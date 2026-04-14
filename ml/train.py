import os
import pandas as pd
from sqlalchemy import create_engine
from sklearn.ensemble import IsolationForest
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
import mlflow
import mlflow.sklearn

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost/fraud_db")
MLFLOW_URL = os.getenv("MLFLOW_URL", "http://localhost:5000")

def load_data():
    print("Loading data from database...")
    engine = create_engine(DATABASE_URL)
    query = "SELECT amount, merchant_category, timestamp FROM transactions"
    df = pd.read_sql(query, engine)
    
    # Feature Engineering
    if not df.empty:
        # Extract hour from timestamp
        df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
        df.drop(columns=['timestamp'], inplace=True)
    return df

def train_and_log_model():
    mlflow.set_tracking_uri(MLFLOW_URL)
    mlflow.set_experiment("Fraud_Anomaly_Detection")
    
    df = load_data()
    if df.empty:
        print("No training data available. Run producer for a while.")
        return
        
    print(f"Training model on {len(df)} transactions...")
    
    X = df[['amount', 'merchant_category', 'hour']]
    
    # Pipeline
    numeric_features = ['amount', 'hour']
    categorical_features = ['merchant_category']
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ])
        
    model = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', IsolationForest(contamination=0.05, random_state=42))
    ])
    
    with mlflow.start_run() as run:
        model.fit(X)
        
        # Log and register model
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="isolation_forest",
            registered_model_name="fraud_iforest"
        )
        print(f"Model logged in run {run.info.run_id}")

if __name__ == "__main__":
    train_and_log_model()
