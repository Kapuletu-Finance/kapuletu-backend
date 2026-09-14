import subprocess
import os
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.ai_feedback import AIFeedback
from models.pending_transaction import PendingTransaction
from models.system_config import SystemConfig
import datetime
import uuid

class AIGovernanceService:
    """
    AIGovernanceService: Manages the lifecycle of AI training data and model deployment.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_config(self):
        """Retrieves global AI training configuration."""
        config = self.db.query(SystemConfig).filter(SystemConfig.config_key == "ai_training_config").first()
        if not config:
            return {"training_mode": "periodic", "continuous_threshold": 50}
        return config.config_value

    def update_config(self, new_config: dict):
        """Updates global AI training configuration."""
        config = self.db.query(SystemConfig).filter(SystemConfig.config_key == "ai_training_config").first()
        if not config:
            config = SystemConfig(config_key="ai_training_config", config_value=new_config)
            self.db.add(config)
        else:
            config.config_value = new_config
        self.db.commit()
        return True

    def get_feedback_queue(self):
        """
        Lists corrections made by treasurers that have not yet been reviewed by an admin.
        """
        feedback = self.db.query(AIFeedback).filter(AIFeedback.is_reviewed == False).all()
        return [{
            "feedback_id": str(f.feedback_id),
            "user_id": str(f.user_id),
            "original": f.original_parsed_data,
            "corrected": f.corrected_data,
            "created_at": f.created_at.isoformat()
        } for f in feedback]

    def approve_feedback(self, feedback_id: str, admin_id: str, approved: bool = True):
        """
        Marks a correction as approved for the next training cycle.
        """
        fb = self.db.query(AIFeedback).filter(AIFeedback.feedback_id == feedback_id).first()
        if not fb:
            return False
            
        fb.is_reviewed = True
        fb.is_approved_for_training = approved
        fb.reviewed_by = admin_id
        fb.reviewed_at = datetime.datetime.utcnow()
        
        self.db.commit()
        return True

    def get_training_pool(self):
        """
        Retrieves all approved ground-truth samples (Treasurer corrections + Manual entries).
        """
        approved = self.db.query(AIFeedback).filter(AIFeedback.is_approved_for_training == True).all()
        return [{
            "id": str(f.feedback_id),
            "text": self.db.query(PendingTransaction).filter(PendingTransaction.pending_id == parse_uuid(f.pending_transaction_id)).first().raw_message,
            "ground_truth": f.corrected_data,
            "source": "treasurer_correction"
        } for f in approved]

    def add_training_sample(self, text: str, ground_truth: dict):
        """
        Allows an admin to manually inject a perfect training sample into the pool.
        """
        # Create a synthetic feedback record
        fb = AIFeedback(
            pending_transaction_id=uuid.uuid4(), # Placeholder ID
            user_id=uuid.uuid4(), # System/Admin ID
            original_parsed_data={},
            corrected_data=ground_truth,
            is_reviewed=True,
            is_approved_for_training=True
        )
        self.db.add(fb)
        self.db.commit()
        return str(fb.feedback_id)

    def trigger_training(self, epochs: int = 10):
        """
        Invokes the AI training script. 
        In production, this would trigger an asynchronous job (e.g. SageMaker).
        """
        # 1. Fetch all approved feedback to build a training set (simulation)
        approved_count = self.db.query(AIFeedback).filter(AIFeedback.is_approved_for_training == True).count()
        
        # 2. Trigger asynchronous job (SageMaker / AWS Batch simulation)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"SAGEMAKER_TRIGGER_SIMULATED: Initiating AI retraining with {approved_count} samples for {epochs} epochs.")
        
        try:
            return {
                "status": "training_queued_sagemaker",
                "samples_included": approved_count,
                "epochs": epochs,
                "engine": "SpaCy v3"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def log_treasurer_correction(self, pending_id, user_id, original, corrected):
        """
        Captures a ground-truth correction from the treasurer.
        """
        # Only log if there is an actual difference
        if original == corrected:
            return
            
        feedback = AIFeedback(
            pending_transaction_id=pending_id,
            user_id=user_id,
            original_parsed_data=original,
            corrected_data=corrected
        )
        self.db.add(feedback)
        self.db.commit()

        # Continuous training disabled to prevent DoS attacks.
        # AI Retraining must be triggered manually via the /ai/parser/train endpoint.
