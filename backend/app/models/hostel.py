"""Tenant-scoped hostel accommodation, welfare and roll-call models."""
import enum, uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.database import Base
from app.models.parent import ParentStudentLink  # noqa: F401  (re-exported for hostel_service's guardian fence)
from app.models.principal import LeaveStatus  # shared PG enum `leave_status`
from app.models.user import Gender

class AllotmentStatus(str, enum.Enum): ACTIVE="ACTIVE"; VACATED="VACATED"; TRANSFERRED="TRANSFERRED"
class HostelAttendanceStatus(str, enum.Enum): PRESENT="PRESENT"; ABSENT="ABSENT"; ON_LEAVE="ON_LEAVE"
class ComplaintStatus(str, enum.Enum): OPEN="OPEN"; IN_PROGRESS="IN_PROGRESS"; RESOLVED="RESOLVED"

class HostelBlock(Base):
 __tablename__="hostel_blocks"; __table_args__=(UniqueConstraint("tenant_id","name",name="uq_hostel_blocks_tenant_name"),)
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); name:Mapped[str]=mapped_column(String(100)); gender:Mapped[Gender]=mapped_column(SAEnum(Gender,name="gender")); warden_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); total_rooms:Mapped[int]=mapped_column(default=0); total_capacity:Mapped[int]=mapped_column(default=0); is_active:Mapped[bool]=mapped_column(Boolean,default=True)
class HostelRoom(Base):
 __tablename__="hostel_rooms"; __table_args__=(UniqueConstraint("block_id","room_number",name="uq_hostel_rooms__block_id_room_number"),)
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); block_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("hostel_blocks.id",ondelete="CASCADE")); room_number:Mapped[str]=mapped_column(String(20)); floor:Mapped[int]=mapped_column(SmallInteger,default=0); capacity:Mapped[int]=mapped_column(SmallInteger,default=2); room_type:Mapped[str]=mapped_column(String(30),default="SHARED"); monthly_fee:Mapped[Decimal]=mapped_column(Numeric(10,2)); amenities:Mapped[list[str]|None]=mapped_column(ARRAY(Text)); is_active:Mapped[bool]=mapped_column(Boolean,default=True)
class HostelAllotment(Base):
 __tablename__="hostel_allotments"; __table_args__=(Index("uq_hostel_active_student","student_id",unique=True,postgresql_where="status = 'ACTIVE'"),Index("uq_hostel_active_bed","room_id","bed_number",unique=True,postgresql_where="status = 'ACTIVE'"))
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); student_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); room_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("hostel_rooms.id")); academic_year_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("academic_years.id")); bed_number:Mapped[int]=mapped_column(SmallInteger); allotted_from:Mapped[date]=mapped_column(Date); allotted_to:Mapped[date|None]=mapped_column(Date); allotted_by:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); status:Mapped[AllotmentStatus]=mapped_column(SAEnum(AllotmentStatus,name="allotment_status")); created_at:Mapped[datetime]=mapped_column(TIMESTAMP(timezone=True),server_default=func.now())
class HostelAttendance(Base):
 __tablename__="hostel_attendance"; __table_args__=(UniqueConstraint("student_id","date",name="uq_hostel_attendance__student_id_date"),)
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); room_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("hostel_rooms.id")); student_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); date:Mapped[date]=mapped_column(Date); status:Mapped[HostelAttendanceStatus]=mapped_column(SAEnum(HostelAttendanceStatus,name="hostel_attendance_status")); marked_by:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); marked_at:Mapped[datetime]=mapped_column(TIMESTAMP(timezone=True),server_default=func.now())
class HostelLeaveRequest(Base):
 __tablename__="hostel_leave_requests"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); student_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); from_date:Mapped[date]=mapped_column(Date); to_date:Mapped[date]=mapped_column(Date); reason:Mapped[str]=mapped_column(Text); destination:Mapped[str|None]=mapped_column(Text); contact_during_leave:Mapped[str|None]=mapped_column(String(20)); status:Mapped[LeaveStatus]=mapped_column(SAEnum(LeaveStatus,name="leave_status")); reviewed_by:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); reviewed_at:Mapped[datetime|None]=mapped_column(TIMESTAMP(timezone=True)); created_at:Mapped[datetime]=mapped_column(TIMESTAMP(timezone=True),server_default=func.now())
class HostelComplaint(Base):
 __tablename__="hostel_complaints"
 id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("tenants.id",ondelete="CASCADE")); student_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); room_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("hostel_rooms.id")); category:Mapped[str]=mapped_column(String(50)); description:Mapped[str]=mapped_column(Text); status:Mapped[ComplaintStatus]=mapped_column(SAEnum(ComplaintStatus,name="complaint_status")); resolved_by:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id")); resolved_at:Mapped[datetime|None]=mapped_column(TIMESTAMP(timezone=True)); created_at:Mapped[datetime]=mapped_column(TIMESTAMP(timezone=True),server_default=func.now())
