"""
Pydantic models for LastMile OS API.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional


# ==================== AUTH MODELS ====================

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str  # agent, coordinator, executive, developer

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    created_at: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ==================== CLIENT / PROVIDER MODELS ====================

class ClientBase(BaseModel):
    name: str

class ClientResponse(ClientBase):
    id: str

class ProviderBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

class ProviderResponse(ProviderBase):
    id: str


# ==================== PACKAGE MODELS ====================

class PackageBase(BaseModel):
    tracking_number: str
    recipient_name: str
    address: str
    zone: str
    delivery_window: str
    status: str = "pending"
    failure_reason: Optional[str] = None

class PackageResponse(PackageBase):
    id: str
    journey_id: str


# ==================== JOURNEY MODELS ====================

class JourneyStartData(BaseModel):
    departure_time: str
    odometer_start: int = 0
    fuel_level: str = ""
    vehicle_condition: str = ""
    vehicle_notes: Optional[str] = None
    packages_loaded: int = 0
    notes: Optional[str] = None
    checklist_completed: bool = True
    arrival_time_cedis: Optional[str] = None
    backup_driver_name: Optional[str] = None
    backup_request_time: Optional[str] = None
    backup_arrival_time: Optional[str] = None
    route_type: Optional[str] = None
    city: Optional[str] = None
    max_packages: Optional[int] = None

    class Config:
        extra = "allow"

class JourneyCloseData(BaseModel):
    closed_at: str
    odometer_end: int
    packages_delivered: int
    packages_failed: int
    notes: Optional[str] = None
    failed_packages: List[dict] = []
    checklist_completed: bool

class JourneyCreate(BaseModel):
    date: str
    client_id: str
    provider_id: str
    packages: List[dict]
    retry_packages: List[str] = []
    route_type: Optional[str] = "CDMX / Zona Metro"
    city: Optional[str] = None
    max_packages: Optional[int] = None

class JourneyResponse(BaseModel):
    id: str
    date: str
    client_id: str
    client_name: Optional[str] = None
    provider_id: str
    provider_name: Optional[str] = None
    status: str
    packages_total: int
    packages_delivered: int
    packages_failed: int
    packages_retry: int
    incidents_count: int
    start_data: Optional[dict] = None
    close_data: Optional[dict] = None
    created_at: str

class CosmoJourneyCreate(BaseModel):
    date: str
    client_id: str
    history_orders: List[dict]
    route_summary: List[dict]
    messenger_provider_mappings: List[dict]
    route_type: Optional[str] = "CDMX / Zona Metro"
    city: Optional[str] = None
    max_packages: Optional[int] = None


# ==================== INCIDENT MODELS ====================

class IncidentBase(BaseModel):
    journey_id: str
    occurred_at: str
    incident_type: str
    description: str
    severity: str  # Alto, Medio, Bajo
    tracking_number: Optional[str] = None
    action_taken: Optional[str] = None
    imputability: Optional[str] = "Por definir"

class IncidentCreate(IncidentBase):
    pass

class IncidentResponse(IncidentBase):
    id: str
    status: str  # open, resolved
    created_at: str
    resolved_at: Optional[str] = None


# ==================== PASSWORD RESET MODELS ====================

class PasswordResetRequest(BaseModel):
    user_id: str
    requested_at: str
    status: str
    notes: Optional[str] = None

class PasswordResetRequestCreate(BaseModel):
    email: EmailStr

class PasswordChangeByAdmin(BaseModel):
    user_id: str
    new_password: str


# ==================== REPORT MODELS ====================

class ReportRequest(BaseModel):
    date_from: str
    date_to: str
    sections: List[str] = []
    group_by: Optional[str] = "provider"


# ==================== MESSENGER MAPPING MODELS ====================

class MessengerProviderMapping(BaseModel):
    messenger_name: str
    provider_id: str


# ==================== BULK UPDATE MODELS ====================

class BulkStatusUpdate(BaseModel):
    package_ids: list[str]
    new_status: str  # pending, delivered, failed, returned
