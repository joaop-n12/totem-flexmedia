from datetime import datetime
from app.extensions import db


class InteractionLog(db.Model):
    """Records every visitor interaction (voice or text) for analytics."""
    __tablename__ = "interaction_logs"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    input_text     = db.Column(db.Text)
    input_type     = db.Column(db.String(10), default="text")  # 'voice' | 'text'
    response_text  = db.Column(db.Text)
    session_id     = db.Column(db.String(64))
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    institution    = db.relationship("Institution", back_populates="logs")

    def __repr__(self):
        return f"<Log {self.id} [{self.input_type}]>"
