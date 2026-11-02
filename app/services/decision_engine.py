# app/services/decision_engine.py

def get_risk_assessment(probability: float, amount: float = 0.0) -> dict:
    """
    Enterprise Hybrid Fraud Decision Engine:
    Combines XGBoost probability with deterministic regulatory, AML, and credit limits.
    """
    # 1. Invalid or Zero / Negative Amount (Carding Probe / Faulty Auth)
    if amount <= 0.0:
        return {
            "risk_level": "HIGH",
            "action": "BLOCK_INVALID_AMOUNT",
            "reason": "Non-positive or zero-authorization transaction amount detected (automated carding probe signature)."
        }
    
    # 2. Extreme Transaction Limit Breach (e.g. > $50,000 or absurd test values like $20,000,000,000)
    if amount > 50000.0:
        return {
            "risk_level": "CRITICAL",
            "action": "BLOCK_LIMIT_EXCEEDED",
            "reason": f"Transaction amount (${amount:,.2f}) breaches institutional retail card limits and anti-smurfing ceiling thresholds."
        }
    
    # 3. Bank Secrecy Act (BSA) & Currency Transaction Report (CTR) regulatory threshold ($10,000)
    if amount >= 10000.0:
        if probability >= 0.50:
            return {
                "risk_level": "CRITICAL",
                "action": "FREEZE_AML_SAR",
                "reason": "High-value transfer exceeding $10,000 BSA threshold with concurrent anomalous telemetry."
            }
        else:
            return {
                "risk_level": "MEDIUM",
                "action": "REVIEW_AML_CTR",
                "reason": "Exceeds $10,000 Bank Secrecy Act CTR threshold. Mandatory AML documentation and KYC review required."
            }
    
    # 4. Standard XGBoost Probability Thresholds
    if probability >= 0.80:
        return {
            "risk_level": "HIGH",
            "action": "BLOCK",
            "reason": "High-confidence multi-dimensional anomaly detected across PCA behavioral vector."
        }
    elif probability >= 0.50:
        return {
            "risk_level": "MEDIUM",
            "action": "REVIEW_REQUIRED",
            "reason": "Elevated statistical divergence requiring 3DS2 Step-Up Authentication."
        }
    else:
        return {
            "risk_level": "LOW",
            "action": "APPROVE",
            "reason": "Within normal Gaussian baseline bounds for genuine cardholder behavior."
        }