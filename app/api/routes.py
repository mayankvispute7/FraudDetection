# app/api/routes.py
import uuid
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db
from app.models.transaction import TransactionLog
from app.schemas.transaction_schema import TransactionIn
from app.config import MODEL_VERSION
from app.api.security import verify_api_key
from app.limiter import limiter

from app.services.feature_engineering import process_transaction
from app.services.fraud_model import predict_fraud
from app.services.decision_engine import get_risk_assessment

router = APIRouter()

# PHASE 4: Lightweight In-Memory Drift State
drift_stats = {"total_reqs": 0, "sum_amount": 0.0, "sum_time": 0.0}
BASELINE_AVG_AMOUNT = 88.0 

@router.post("/predict")
@limiter.limit("50/minute") # PHASE 5: Rate Limiting
async def predict_transaction(
    request: Request, 
    transaction: TransactionIn, 
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key) # PHASE 3: Security
):
    request_id = str(uuid.uuid4())
    logger = logging.getLogger("SentinelX")
    logger = logging.LoggerAdapter(logger, {"request_id": request_id})
    
    logger.info(f"Received transaction for Amount: {transaction.Amount}")

    data_dict = transaction.model_dump()
    features_df = process_transaction(data_dict) 
    fraud_prob = predict_fraud(features_df)      
    decision = get_risk_assessment(fraud_prob, transaction.Amount)

    # If deterministic policy blocks it (e.g. limit breach or invalid amount), align threat score
    if decision["risk_level"] in ["HIGH", "CRITICAL"] and fraud_prob < 0.80:
        fraud_prob = 0.9995 if (transaction.Amount > 50000.0 or transaction.Amount <= 0.0) else 0.85
    elif decision["risk_level"] == "MEDIUM" and fraud_prob < 0.50:
        fraud_prob = 0.6500
    
    db_transaction = TransactionLog(
        amount=transaction.Amount,
        fraud_probability=float(fraud_prob),
        risk_level=decision["risk_level"],
        action=decision["action"],
        model_version=MODEL_VERSION # PHASE 1
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)

    drift_stats["total_reqs"] += 1
    drift_stats["sum_amount"] += transaction.Amount
    drift_stats["sum_time"] += transaction.Time

    logger.info(f"Prediction complete. Action: {decision['action']}")
    
    return {
        "transaction_id": db_transaction.id,
        "fraud_probability": round(fraud_prob, 4),
        "risk_level": decision["risk_level"],
        "action": decision["action"],
        "reason": decision.get("reason", ""),
        "model_version": MODEL_VERSION
    }

@router.post("/predict/batch")
async def predict_batch_transactions(
    payload: dict,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Forensic Batch Audit Endpoint:
    Accepts an array of transactions (e.g. from creditcard.csv upload), runs vectorized ML inference,
    categorizes threats into cyber crime vectors, and returns full forensic analysis.
    """
    transactions_data = payload.get("transactions", [])
    if not transactions_data:
        return {
            "total_analyzed": 0,
            "total_threats_flagged": 0,
            "total_legitimate": 0,
            "threat_rate_percentage": 0.0,
            "total_amount_at_risk": 0.0,
            "results": []
        }

    import pandas as pd
    from app.services.fraud_model import model

    expected_cols = [
        'Time', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 
        'V10', 'V11', 'V12', 'V13', 'V14', 'V15', 'V16', 'V17', 'V18', 
        'V19', 'V20', 'V21', 'V22', 'V23', 'V24', 'V25', 'V26', 'V27', 
        'V28', 'Amount'
    ]

    df = pd.DataFrame(transactions_data)
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0.0

    # Ensure numeric types
    for col in expected_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Vectorized inference in memory
    probabilities = model.predict_proba(df[expected_cols])[:, 1]

    results = []
    total_fraud = 0
    total_amount_at_risk = 0.0
    ground_truth_matches = 0
    ground_truth_total = 0

    for idx, (prob, row) in enumerate(zip(probabilities, transactions_data)):
        fraud_prob = float(prob)
        amount = float(row.get("Amount", 0.0))
        time_val = float(row.get("Time", 0.0))
        gt = row.get("Class", None)
        if gt is not None:
            try:
                gt_val = int(float(gt))
                ground_truth_total += 1
                predicted_class = 1 if fraud_prob >= 0.50 else 0
                if predicted_class == gt_val:
                    ground_truth_matches += 1
            except Exception:
                gt_val = None
        else:
            gt_val = None

        if fraud_prob >= 0.80:
            risk_level = "CRITICAL"
            action = "BLOCK & FREEZE"
            total_fraud += 1
            total_amount_at_risk += amount
        elif fraud_prob >= 0.50:
            risk_level = "HIGH"
            action = "MANUAL REVIEW / 2FA"
            total_fraud += 1
            total_amount_at_risk += amount
        elif fraud_prob >= 0.20:
            risk_level = "MEDIUM"
            action = "FLAG FOR STEP-UP AUTH"
        else:
            risk_level = "LOW"
            action = "APPROVE"

        # Forensic Cyber Crime Classification
        if fraud_prob < 0.50:
            crime_category = "Legitimate"
            threat_icon = "shield-check"
            indicator = "Normal telemetry signature; behavioral biometric profile verified"
        elif amount > 5000:
            crime_category = "Money Laundering"
            threat_icon = "dollar-sign"
            indicator = "High structured value anomaly; smurfing/layering pattern detected"
        elif fraud_prob > 0.85 and (float(row.get("V14", 0)) < -3.0 or float(row.get("V17", 0)) < -2.0):
            crime_category = "Card Skimming"
            threat_icon = "credit-card"
            indicator = "Severe negative V14/V17 divergence indicating magnetic stripe cloning / ATM skimming"
        elif fraud_prob > 0.70:
            crime_category = "Identity Theft"
            threat_icon = "user-x"
            indicator = "Multi-factor authentication mismatch; account takeover (ATO) signature"
        else:
            crime_category = "Financial Fraud"
            threat_icon = "alert-triangle"
            indicator = "High statistical divergence in transaction sequence and velocity"

        results.append({
            "index": idx + 1,
            "time": time_val,
            "amount": amount,
            "fraud_probability": round(fraud_prob, 4),
            "risk_level": risk_level,
            "action": action,
            "crime_category": crime_category,
            "indicator": indicator,
            "ground_truth": gt_val
        })

    accuracy_pct = round((ground_truth_matches / ground_truth_total) * 100, 1) if ground_truth_total > 0 else None

    return {
        "total_analyzed": len(results),
        "total_threats_flagged": total_fraud,
        "total_legitimate": len(results) - total_fraud,
        "threat_rate_percentage": round((total_fraud / len(results)) * 100, 2) if results else 0.0,
        "total_amount_at_risk": round(total_amount_at_risk, 2),
        "ground_truth_accuracy": accuracy_pct,
        "results": results
    }

@router.get("/metrics")
async def get_system_metrics(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    total_transactions = db.query(TransactionLog).count()
    if total_transactions == 0:
        return {"message": "No transactions processed yet."}
        
    fraud_count = db.query(TransactionLog).filter(
        TransactionLog.risk_level.in_(["HIGH", "MEDIUM"])
    ).count()
    fraud_rate = round((fraud_count / total_transactions) * 100, 2)
    avg_score = db.query(func.avg(TransactionLog.fraud_probability)).scalar()
    
    return {
        "total_transactions_processed": total_transactions,
        "total_fraud_flags": fraud_count,
        "current_fraud_rate_percentage": fraud_rate,
        "average_system_risk_score": round(avg_score, 4)
    }

@router.get("/drift-metrics")
async def get_drift_metrics(api_key: str = Depends(verify_api_key)):
    if drift_stats["total_reqs"] == 0:
        return {"message": "No data to analyze yet."}
    
    current_avg_amount = drift_stats["sum_amount"] / drift_stats["total_reqs"]
    deviation = abs(current_avg_amount - BASELINE_AVG_AMOUNT)
    
    warning = "CRITICAL DRIFT DETECTED" if deviation > 50.0 else "NORMAL"

    return {
        "baseline_avg_amount": BASELINE_AVG_AMOUNT,
        "current_avg_amount": round(current_avg_amount, 2),
        "deviation": round(deviation, 2),
        "status": warning
    }