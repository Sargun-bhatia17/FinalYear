class FusionEngine:
    def __init__(self, repository):
        self.repository = repository

    def calculate_weights(self) -> tuple[float, float]:
        """
        Calculates W_ml and W_rule based on the session count N in the database.
        W_ml = min(0.8, N / 500)
        W_rule = 1.0 - W_ml
        """
        try:
            N = self.repository.get_session_count()
        except Exception:
            N = 0
            
        w_ml = min(0.8, N / 500.0)
        w_rule = 1.0 - w_ml
        return w_ml, w_rule

    def fuse_scores(self, 
                    ml_predicted_state: str, 
                    ml_risk_score: float, 
                    rule_state: str, 
                    rule_risk_score: float, 
                    rule_override_triggered: bool) -> tuple[str, float]:
        """
        Blends the ML model classification and Rule Engine results.
        Returns:
            Tuple[str, float]: (final_state, final_attention_risk_score)
        """
        w_ml, w_rule = self.calculate_weights()
        
        if rule_override_triggered:
            # If an explicit override rule is triggered, let the rule dictate the final state,
            # and blend the risk scores with the permanent rule-floor weight.
            final_state = rule_state
            final_risk = (rule_risk_score * w_rule) + (ml_risk_score * w_ml)
        else:
            # No override: ML predicts the state, and scores are blended.
            final_state = ml_predicted_state
            
            # For baseline rule score when no override is active, we can match the ML score
            # or reference a category baseline. Let's blend ml_risk_score with a category baseline
            # if we want, or simple blend:
            final_risk = ml_risk_score  # As no override rules are triggered, ML drives it.
            
        # Ensure final risk is capped between 0.0 and 1.0
        final_risk = max(0.0, min(1.0, final_risk))
        
        return final_state, final_risk
