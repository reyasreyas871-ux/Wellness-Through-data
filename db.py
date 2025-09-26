from datetime import datetime, date
from typing import Optional
from sqlalchemy import Integer,String,DateTime,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from datetime import datetime

from sqlalchemy import create_engine, Integer, String, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DB_URL = "sqlite:///amr.db"

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(10))
    prescriptions: Mapped[list["Prescription"]] = relationship(back_populates="patient")

class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    antibiotic: Mapped[str] = mapped_column(String(120))
    dosage_mg: Mapped[int] = mapped_column(Integer)
    frequency_per_day: Mapped[int] = mapped_column(Integer)
    days: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient: Mapped["Patient"] = relationship(back_populates="prescriptions")
    adherence_logs: Mapped[list["AdherenceLog"]] = relationship(back_populates="prescription")

class AdherenceLog(Base):
    __tablename__ = "adherence_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"))
    taken: Mapped[bool] = mapped_column(Boolean)  # True=dose taken, False=missed
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    prescription: Mapped["Prescription"] = relationship(back_populates="adherence_logs")

from typing import Optional  # you already have this
from sqlalchemy import Text  # add if not present

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"))
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PharmacyDispense(Base):
    __tablename__ = "pharmacy_dispense"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"))
    pharmacy_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class IotDose(Base):
    """
    A “pending/taken/missed/opened” IoT dose event that is resolved by patient confirmation.
    When resolved, we also insert into AdherenceLog to keep your metrics working.
    """
    __tablename__ = "iot_doses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"))
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dose_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|taken|missed|opened
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # blister|patient|pharmacy
    token: Mapped[str] = mapped_column(String(64), unique=True)  # for confirmation link
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # relationship to Prescription so we can access details like p.patient_name
    prescription = relationship("Prescription", backref="iot_doses")


def init_db():
    Base.metadata.create_all(engine)

def get_session():
    return SessionLocal()