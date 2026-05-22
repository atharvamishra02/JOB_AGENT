"""
Database layer — SQLAlchemy ORM models & CRUD operations.

Default: SQLite (zero-config).
Upgrade:  change DATABASE_URL to a PostgreSQL URI and it Just Works™.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, relationship


# ── ORM Base ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    """Registered user — supports email/password and OAuth providers."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    name = Column(String(256), default="")
    picture = Column(Text, default="")
    provider = Column(String(32), default="email")  # email | google | github
    hashed_password = Column(Text, default="")       # empty for OAuth users
    
    # AI Settings (User-owned keys)
    openai_api_key = Column(Text, default="")
    gemini_api_key = Column(Text, default="")
    preferred_model = Column(String(64), default="gpt-4o") # gpt-4o | gemini-1.5-pro | etc.
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    applications = relationship("ApplicationLog", back_populates="user", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r}, provider={self.provider!r})>"


class ApplicationLog(Base):
    """Tracks every application attempt — the single source of truth."""

    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    job_id = Column(String(256), nullable=False, index=True)
    company = Column(String(256), nullable=False)
    title = Column(String(512), nullable=False)
    url = Column(Text, default="")
    match_score = Column(Float, default=0.0)
    decision = Column(String(32), default="")          # apply | skip | ask
    status = Column(String(32), default="pending")     # applied | failed | skipped | duplicate
    error = Column(Text, default="")
    optimized_resume_snippet = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="applications")

    # Prevent duplicate applications to the same job per user
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ApplicationLog(job_id={self.job_id!r}, company={self.company!r}, "
            f"status={self.status!r})>"
        )


# ── Engine / Session factory ─────────────────────────────────────────────────

_DEFAULT_DB_URL = "sqlite:///./job_agent.db"


def get_engine(url: str | None = None):
    db_url = url or os.getenv("DATABASE_URL", _DEFAULT_DB_URL)
    # SQLite needs check_same_thread=False for multi-threaded use
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, echo=False, connect_args=connect_args)


def get_session_factory(url: str | None = None) -> sessionmaker:
    engine = get_engine(url)
    return sessionmaker(bind=engine)


def init_db(url: str | None = None) -> sessionmaker:
    """Create tables and return a session factory."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


# ── CRUD helpers ─────────────────────────────────────────────────────────────

def is_duplicate(session: Session, job_id: str) -> bool:
    """Check if we already applied to this job_id."""
    return (
        session.query(ApplicationLog)
        .filter_by(job_id=job_id, status="applied")
        .first()
        is not None
    )


def insert_application(session: Session, record: dict) -> ApplicationLog:
    """Insert a new application log entry.  Returns the ORM object."""
    log = ApplicationLog(**record)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.query(User).filter(User.id == user_id).first()


def update_user_settings(session: Session, user_id: int, settings: dict) -> User | None:
    """Update a user's API keys and model preferences."""
    user = get_user_by_id(session, user_id)
    if not user:
        return None
    
    if "openai_api_key" in settings:
        user.openai_api_key = settings["openai_api_key"]
    if "gemini_api_key" in settings:
        user.gemini_api_key = settings["gemini_api_key"]
    if "preferred_model" in settings:
        user.preferred_model = settings["preferred_model"]
    if "name" in settings:
        user.name = settings["name"]
        
    session.commit()
    return user


def get_all_applications(session: Session, user_id: int | None = None) -> list[ApplicationLog]:
    """Return every logged application, newest first. Optionally filter by user."""
    query = session.query(ApplicationLog)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.order_by(ApplicationLog.created_at.desc()).all()


# ── User CRUD ────────────────────────────────────────────────────────────────

def get_user_by_email(session: Session, email: str) -> User | None:
    return session.query(User).filter_by(email=email).first()


def create_user(session: Session, email: str, name: str = "", picture: str = "",
                provider: str = "email", hashed_password: str = "") -> User:
    user = User(
        email=email,
        name=name,
        picture=picture,
        provider=provider,
        hashed_password=hashed_password,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_or_create_oauth_user(session: Session, email: str, name: str,
                              picture: str, provider: str) -> User:
    """Find existing user by email or create a new one for OAuth login."""
    user = get_user_by_email(session, email)
    if user:
        # Update profile info from OAuth provider
        user.name = name or user.name
        user.picture = picture or user.picture
        if user.provider == "email":
            user.provider = provider  # Upgrade to OAuth if they originally used email
        session.commit()
        return user
    return create_user(session, email, name, picture, provider)
