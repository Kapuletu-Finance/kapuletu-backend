from sqlalchemy.orm import Session
from uuid import UUID

class BaseRepository:
    def __init__(self, db: Session, model):
        self.db = db
        self.model = model

    def get_by_id(self, id: UUID, owner_id: UUID = None):
        query = self.db.query(self.model).filter(self.model.id == id)
        if owner_id:
            query = query.filter(self.model.owner_id == owner_id)
        return query.first()

    def get_all(self, owner_id: UUID = None, skip: int = 0, limit: int = 100):
        query = self.db.query(self.model)
        if owner_id:
            query = query.filter(self.model.owner_id == owner_id)
        return query.offset(skip).limit(limit).all()

    def create(self, obj_in):
        self.db.add(obj_in)
        self.db.commit()
        self.db.refresh(obj_in)
        return obj_in

    def update(self, db_obj, obj_in):
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
