import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from confluent_kafka import Consumer, KafkaError
import pandas as pd
import mlflow.sklearn

from models import SessionLocal, Transaction, Alert, AuditLog
from enrichment import update_user_features
from scoring import calculate_risk_score
from notifications import send_critical_alert

app = FastAPI(title="Fraud Detection Engine")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:29092")
TOPIC = "transactions_in"
GROUP_ID = "fraud_detection_group"

consumer_conf = {
    'bootstrap.servers': KAFKA_BROKER,
    'group.id': GROUP_ID,
    'auto.offset.reset': 'earliest'
}

ml_model = None

def load_ml_model():
    global ml_model
    try:
        mlflow.set_tracking_uri(os.getenv("MLFLOW_URL", "http://localhost:5000"))
        model_uri = "models:/fraud_iforest/latest"
        print(f"Loading ML model from {model_uri}...")
        ml_model = mlflow.sklearn.load_model(model_uri)
        print("ML model loaded successfully.")
    except Exception as e:
        print(f"Warning: Could not load ML model. ML scoring is disabled. Error: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def evaluate_transaction(transaction: dict, user_tx_count: int):
    amount = float(transaction.get('amount', 0))
    ts = datetime.fromisoformat(transaction['timestamp'])
    
    rules_triggered = []
    
    # 1. Base Rules Check
    if amount > 10000:
        rules_triggered.append("HIGH_AMOUNT_THRESHOLD")
        
    if user_tx_count > 100:
        rules_triggered.append("HIGH_VELOCITY")
    
    # 2. ML Prediction Check
    is_ml_anomaly = False
    if ml_model:
        df = pd.DataFrame([{
            'amount': amount,
            'merchant_category': transaction['merchant_category'],
            'hour': ts.hour
        }])
        pred = ml_model.predict(df)[0]
        if pred == -1:
            rules_triggered.append("ML_BEHAVIORAL_ANOMALY")
            is_ml_anomaly = True
            
    # 3. Aggregate composite risk score
    risk_score = calculate_risk_score(amount, user_tx_count, is_ml_anomaly)
    
    return risk_score, rules_triggered

def process_message(msg_value: str, db: Session):
    try:
        data = json.loads(msg_value)
        ts = datetime.fromisoformat(data['timestamp'])
        
        user_tx_count = update_user_features(data['user_id'], ts)
        
        risk_score, rules_triggered = evaluate_transaction(data, user_tx_count)
        
        # Insert Transaction 
        tx = Transaction(
            transaction_id=data['transaction_id'],
            user_id=data['user_id'],
            amount=data['amount'],
            merchant_category=data['merchant_category'],
            location=data['location'],
            timestamp=ts,
            status='PROCESSED',
            risk_score=risk_score
        )
        db.add(tx)
        db.flush() # Secure Transaction object into the DB sequentially
        
        # Queue actionable alerts based on risk tier
        if risk_score > 40:
            severity = "CRITICAL" if risk_score >= 80 else "MEDIUM"
            rule_string = ",".join(rules_triggered) if rules_triggered else "COMPOSITE_RISK"
            
            alert = Alert(
                transaction_id=data['transaction_id'],
                rule_triggered=rule_string,
                severity=severity,
                created_at=datetime.utcnow()
            )
            db.add(alert)
            
            if risk_score >= 80:
                # Dispatch real-time emergency out-of-band notification
                send_critical_alert(data['transaction_id'], risk_score, rules_triggered)
                # Auto block extreme scenarios
                tx.status = 'BLOCKED'
        
        # Save overarching audit log
        log_details = f"Processed TX. Score: {risk_score}. Velocity: {user_tx_count}."
        audit = AuditLog(
            action="TRANSACTION_PROCESSED",
            entity_id=data['transaction_id'],
            details=log_details,
            timestamp=datetime.utcnow()
        )
        db.add(audit)
        
        db.commit()
    except Exception as e:
        print(f"Error processing message: {e}")
        db.rollback()

async def consume_loop():
    consumer = Consumer(consumer_conf)
    consumer.subscribe([TOPIC])
    print(f"Subscribed to topic {TOPIC}")
    db = SessionLocal()
    try:
        while True:
            await asyncio.sleep(0.1)
            msg = consumer.poll(0.1)
            
            if msg is None: continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print("Kafka Consumer Error:", msg.error())
                    await asyncio.sleep(1)
                    continue
                    
            process_message(msg.value().decode('utf-8'), db)
    finally:
        consumer.close()
        db.close()

@app.on_event("startup")
async def startup_event():
    load_ml_model()
    asyncio.create_task(consume_loop())

@app.get("/")
def read_root():
    return {"status": "Fraud Detection Engine is running in Phase 3 mode"}
