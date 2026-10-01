"""Feedback Campaign service — all business logic for the feedback feature.

Access rules:
  - Institution Admin or Principal: create / manage campaigns, view analytics.
  - Student: see active campaigns (only teachers they study under); submit once per target.
  - Teacher: see aggregated results of campaigns they appear in.

Privacy rules (strictly enforced here, not in the router):
  - student_id is stored for deduplication but NEVER returned to teachers
    unless allow_anonymous=False, in which case comments *may* be shared but
    student identity still is not (only comments, as per the design).
  - Teacher sees only aggregated averages. Individual responses are hidden.
  - Admin/Principal analytics include per-teacher aggregates and can see
    comments when allow_anonymous=False.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, cast, func, or_, select, update, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import SchoolClass, Subject
from app.models.enrollment import Enrollment, EnrollmentStatus, TeacherSubject
from app.models.feedback import CampaignStatus, FeedbackCampaign, FeedbackCampaignTarget, FeedbackResponse
from app.models.online_class import Notification
from app.models.user import User
from app.schemas.feedback import (
    CampaignAnalytics,
    CampaignCreate,
    CampaignDetail,
    CampaignPage,
    CampaignRow,
    CampaignTargetRow,
    CampaignUpdate,
    FeedbackSubmit,
    StudentFeedbackCampaign,
    StudentFeedbackTarget,
    TeacherAggregateResult,
    TeacherFeedbackResult,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class FeedbackService:
    """All business logic for the teacher feedback campaign feature."""

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_campaign_or_404(
        db: AsyncSession, campaign_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> FeedbackCampaign:
        row = (
            await db.execute(
                select(FeedbackCampaign).where(
                    FeedbackCampaign.id == campaign_id,
                    FeedbackCampaign.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Feedback campaign not found")
        return row

    @staticmethod
    async def _build_target_rows(
        db: AsyncSession, targets: list[FeedbackCampaignTarget]
    ) -> list[CampaignTargetRow]:
        if not targets:
            return []

        teacher_ids = {t.teacher_id for t in targets}
        subject_ids = {t.subject_id for t in targets if t.subject_id}
        class_ids = {t.class_id for t in targets if t.class_id}

        teachers = {
            u.id: u.name
            for u in (
                await db.execute(select(User).where(User.id.in_(teacher_ids)))
            ).scalars().all()
        }
        subjects = {
            s.id: s.name
            for s in (
                await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))
            ).scalars().all()
        } if subject_ids else {}
        classes = {
            c.id: c.name
            for c in (
                await db.execute(select(SchoolClass).where(SchoolClass.id.in_(class_ids)))
            ).scalars().all()
        } if class_ids else {}

        return [
            CampaignTargetRow(
                id=t.id,
                teacher_id=t.teacher_id,
                teacher_name=teachers.get(t.teacher_id),
                subject_id=t.subject_id,
                subject_name=subjects.get(t.subject_id) if t.subject_id else None,
                class_id=t.class_id,
                class_name=classes.get(t.class_id) if t.class_id else None,
            )
            for t in targets
        ]

    @staticmethod
    def _to_row(campaign: FeedbackCampaign, target_count: int = 0) -> CampaignRow:
        return CampaignRow(
            id=campaign.id,
            title=campaign.title,
            description=campaign.description,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            allow_anonymous=campaign.allow_anonymous,
            status=campaign.status.value if hasattr(campaign.status, "value") else campaign.status,
            created_at=campaign.created_at,
            closed_at=campaign.closed_at,
            target_count=target_count,
        )

    # ── Admin / Principal — campaign lifecycle ────────────────────────────────

    @staticmethod
    async def create_campaign(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        created_by: uuid.UUID,
        payload: CampaignCreate,
    ) -> CampaignDetail:
        """Create a feedback campaign with its teacher targets."""
        campaign = FeedbackCampaign(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=payload.title,
            description=payload.description,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            allow_anonymous=payload.allow_anonymous,
            status=CampaignStatus.DRAFT,
            created_by=created_by,
        )
        db.add(campaign)
        await db.flush()  # get the id

        target_objects: list[FeedbackCampaignTarget] = []
        seen: set[tuple] = set()
        for t in payload.targets:
            key = (t.teacher_id, t.subject_id)
            if key in seen:
                continue
            seen.add(key)
            obj = FeedbackCampaignTarget(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                teacher_id=t.teacher_id,
                subject_id=t.subject_id,
                class_id=t.class_id,
            )
            db.add(obj)
            target_objects.append(obj)

        await db.flush()
        await db.commit()
        await db.refresh(campaign)

        target_rows = await FeedbackService._build_target_rows(db, target_objects)
        return CampaignDetail(
            **FeedbackService._to_row(campaign, len(target_rows)).model_dump(),
            targets=target_rows,
        )

    @staticmethod
    async def list_campaigns(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CampaignPage:
        base_where = [FeedbackCampaign.tenant_id == tenant_id]
        if status_filter:
            try:
                st = CampaignStatus(status_filter.upper())
                base_where.append(FeedbackCampaign.status == st)
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid status: {status_filter}")

        total = (
            await db.execute(
                select(func.count(FeedbackCampaign.id)).where(*base_where)
            )
        ).scalar_one()

        rows = (
            await db.execute(
                select(FeedbackCampaign)
                .where(*base_where)
                .order_by(FeedbackCampaign.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

        # Count targets per campaign
        campaign_ids = [c.id for c in rows]
        target_counts: dict[uuid.UUID, int] = {}
        if campaign_ids:
            count_rows = (
                await db.execute(
                    select(
                        FeedbackCampaignTarget.campaign_id,
                        func.count(FeedbackCampaignTarget.id),
                    )
                    .where(FeedbackCampaignTarget.campaign_id.in_(campaign_ids))
                    .group_by(FeedbackCampaignTarget.campaign_id)
                )
            ).all()
            target_counts = {r[0]: r[1] for r in count_rows}

        return CampaignPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[FeedbackService._to_row(c, target_counts.get(c.id, 0)) for c in rows],
        )

    @staticmethod
    async def get_campaign(
        db: AsyncSession, campaign_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> CampaignDetail:
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        targets = (
            await db.execute(
                select(FeedbackCampaignTarget).where(
                    FeedbackCampaignTarget.campaign_id == campaign.id
                )
            )
        ).scalars().all()
        target_rows = await FeedbackService._build_target_rows(db, list(targets))
        return CampaignDetail(
            **FeedbackService._to_row(campaign, len(target_rows)).model_dump(),
            targets=target_rows,
        )

    @staticmethod
    async def update_campaign(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: CampaignUpdate,
    ) -> CampaignDetail:
        """Update a campaign — only allowed while it is in DRAFT status."""
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        if campaign.status != CampaignStatus.DRAFT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Only DRAFT campaigns can be updated",
            )
        if payload.title is not None:
            campaign.title = payload.title
        if payload.description is not None:
            campaign.description = payload.description
        if payload.starts_at is not None:
            campaign.starts_at = payload.starts_at
        if payload.ends_at is not None:
            campaign.ends_at = payload.ends_at
        if payload.allow_anonymous is not None:
            campaign.allow_anonymous = payload.allow_anonymous
        if campaign.ends_at <= campaign.starts_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ends_at must be after starts_at")
        await db.flush()
        await db.commit()
        await db.refresh(campaign)
        return await FeedbackService.get_campaign(db, campaign_id, tenant_id)

    @staticmethod
    async def publish_campaign(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> CampaignDetail:
        """Transition DRAFT → ACTIVE and notify students."""
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        if campaign.status != CampaignStatus.DRAFT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Only DRAFT campaigns can be published",
            )
        campaign.status = CampaignStatus.ACTIVE
        await db.flush()

        # Notify all students in the tenant who belong to a class that has
        # at least one targeted teacher → they receive a push + in-app notification.
        await FeedbackService._notify_students_of_campaign(db, campaign, tenant_id)

        await db.commit()
        await db.refresh(campaign)
        return await FeedbackService.get_campaign(db, campaign_id, tenant_id)

    @staticmethod
    async def _notify_students_of_campaign(
        db: AsyncSession,
        campaign: FeedbackCampaign,
        tenant_id: uuid.UUID,
    ) -> None:
        """Send in-app + push notification to all enrolled students in targeted classes."""
        try:
            async with db.begin_nested():
                # Collect class_ids from targets
                targets = (
                    await db.execute(
                        select(FeedbackCampaignTarget).where(
                            FeedbackCampaignTarget.campaign_id == campaign.id,
                            FeedbackCampaignTarget.class_id.is_not(None),
                        )
                    )
                ).scalars().all()
                class_ids = {t.class_id for t in targets if t.class_id}

                if not class_ids:
                    # Fall back to all active enrolled students in the tenant
                    student_ids_rows = (
                        await db.execute(
                            select(Enrollment.student_id).where(
                                Enrollment.tenant_id == tenant_id,
                                cast(Enrollment.status, String) == EnrollmentStatus.ACTIVE.value,
                            )
                        )
                    ).scalars().all()
                else:
                    student_ids_rows = (
                        await db.execute(
                            select(Enrollment.student_id).where(
                                Enrollment.class_id.in_(class_ids),
                                Enrollment.tenant_id == tenant_id,
                                cast(Enrollment.status, String) == EnrollmentStatus.ACTIVE.value,
                            )
                        )
                    ).scalars().all()

                student_ids = list(set(student_ids_rows))
                if not student_ids:
                    return

                await NotificationService.create_notifications(
                    db,
                    tenant_id=tenant_id,
                    user_ids=student_ids,
                    title="Feedback Campaign Open",
                    body=f"Feedback campaign '{campaign.title}' is now open. Feedback window closes {campaign.ends_at.strftime('%d %b %Y')}.",
                    notif_type="FEEDBACK_CAMPAIGN",
                    data={"campaign_id": str(campaign.id)},
                )
        except Exception as exc:  # noqa: BLE001 — notification is best-effort
            logger.warning("Failed to notify students for campaign %s: %s", campaign.id, exc)

    @staticmethod
    async def close_campaign(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> CampaignDetail:
        """Manually close an ACTIVE campaign (also called by the scheduler)."""
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.ACTIVE):
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Campaign is already closed"
            )
        campaign.status = CampaignStatus.CLOSED
        campaign.closed_at = datetime.now(timezone.utc)
        await db.flush()
        await db.commit()
        await db.refresh(campaign)
        return await FeedbackService.get_campaign(db, campaign_id, tenant_id)

    @staticmethod
    async def delete_campaign(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        """Hard-delete a DRAFT campaign (not allowed once published)."""
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        if campaign.status != CampaignStatus.DRAFT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Only DRAFT campaigns can be deleted",
            )
        await db.delete(campaign)
        await db.commit()

    # ── Admin / Principal — analytics ─────────────────────────────────────────

    @staticmethod
    async def get_campaign_analytics(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> CampaignAnalytics:
        """Aggregated results across all teachers in a campaign (admin/principal view)."""
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)

        targets = (
            await db.execute(
                select(FeedbackCampaignTarget).where(
                    FeedbackCampaignTarget.campaign_id == campaign.id
                )
            )
        ).scalars().all()
        if not targets:
            return CampaignAnalytics(
                campaign_id=campaign.id,
                campaign_title=campaign.title,
                total_responses=0,
                results=[],
            )

        target_ids = [t.id for t in targets]

        # Aggregate per target
        agg_rows = (
            await db.execute(
                select(
                    FeedbackResponse.target_id,
                    func.count(FeedbackResponse.id).label("count"),
                    func.avg(FeedbackResponse.teaching_clarity).label("tc_avg"),
                    func.avg(FeedbackResponse.subject_knowledge).label("sk_avg"),
                    func.avg(FeedbackResponse.interaction).label("int_avg"),
                    func.avg(FeedbackResponse.overall).label("ov_avg"),
                )
                .where(FeedbackResponse.target_id.in_(target_ids))
                .group_by(FeedbackResponse.target_id)
            )
        ).all()

        agg_map = {r.target_id: r for r in agg_rows}

        # Comments — only if not anonymous
        comments_map: dict[uuid.UUID, list[str]] = {}
        if not campaign.allow_anonymous:
            comment_rows = (
                await db.execute(
                    select(FeedbackResponse.target_id, FeedbackResponse.comment)
                    .where(
                        FeedbackResponse.target_id.in_(target_ids),
                        FeedbackResponse.comment.is_not(None),
                        FeedbackResponse.comment != "",
                    )
                )
            ).all()
            for r in comment_rows:
                comments_map.setdefault(r.target_id, []).append(r.comment)

        # Resolve teacher names
        teacher_ids = {t.teacher_id for t in targets}
        teachers = {
            u.id: u.name
            for u in (
                await db.execute(select(User).where(User.id.in_(teacher_ids)))
            ).scalars().all()
        }

        # Group targets by teacher (a teacher may have multiple subject targets)
        from collections import defaultdict
        by_teacher: dict[uuid.UUID, list[FeedbackCampaignTarget]] = defaultdict(list)
        for t in targets:
            by_teacher[t.teacher_id].append(t)

        results: list[TeacherAggregateResult] = []
        total_responses = 0

        def _avg(*vals: float | None) -> float | None:
            valid = [v for v in vals if v is not None]
            return round(sum(valid) / len(valid), 2) if valid else None

        for teacher_id, teacher_targets in by_teacher.items():
            t_ids = [t.id for t in teacher_targets]
            counts, tc_avgs, sk_avgs, int_avgs, ov_avgs = [], [], [], [], []
            t_comments: list[str] = []
            for tid in t_ids:
                agg = agg_map.get(tid)
                if agg:
                    counts.append(agg.count)
                    tc_avgs.append(float(agg.tc_avg) if agg.tc_avg is not None else None)
                    sk_avgs.append(float(agg.sk_avg) if agg.sk_avg is not None else None)
                    int_avgs.append(float(agg.int_avg) if agg.int_avg is not None else None)
                    ov_avgs.append(float(agg.ov_avg) if agg.ov_avg is not None else None)
                if tid in comments_map:
                    t_comments.extend(comments_map[tid])

            count = sum(counts)
            total_responses += count
            results.append(
                TeacherAggregateResult(
                    teacher_id=teacher_id,
                    teacher_name=teachers.get(teacher_id),
                    response_count=count,
                    teaching_clarity_avg=_avg(*tc_avgs),
                    subject_knowledge_avg=_avg(*sk_avgs),
                    interaction_avg=_avg(*int_avgs),
                    overall_avg=_avg(*ov_avgs),
                    comments=t_comments if not campaign.allow_anonymous else None,
                )
            )

        return CampaignAnalytics(
            campaign_id=campaign.id,
            campaign_title=campaign.title,
            total_responses=total_responses,
            results=results,
        )

    # ── Student surface ───────────────────────────────────────────────────────

    @staticmethod
    async def list_active_campaigns_for_student(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> list[StudentFeedbackCampaign]:
        """Return all ACTIVE campaigns with targets filtered to the student's own teachers."""
        now = datetime.now(timezone.utc)

        # Active campaigns in this tenant
        campaigns = (
            await db.execute(
                select(FeedbackCampaign).where(
                    FeedbackCampaign.tenant_id == tenant_id,
                    FeedbackCampaign.status == CampaignStatus.ACTIVE,
                    FeedbackCampaign.starts_at <= now,
                    FeedbackCampaign.ends_at > now,
                )
            )
        ).scalars().all()
        if not campaigns:
            return []

        # Resolve which classes the student is enrolled in
        student_class_ids = set(
            (
                await db.execute(
                    select(Enrollment.class_id).where(
                        Enrollment.student_id == student_id,
                        cast(Enrollment.status, String) == EnrollmentStatus.ACTIVE.value,
                    )
                )
            ).scalars().all()
        )
        if not student_class_ids:
            return []

        # Teachers this student studies under (via teacher_subjects)
        student_teachers = (
            await db.execute(
                select(
                    TeacherSubject.teacher_id,
                    TeacherSubject.subject_id,
                    Subject.class_id,
                )
                .join(Subject, TeacherSubject.subject_id == Subject.id)
                .where(Subject.class_id.in_(student_class_ids))
            )
        ).all()
        student_teacher_ids = {r.teacher_id for r in student_teachers}
        student_teacher_subject_pairs = {(r.teacher_id, r.subject_id) for r in student_teachers}

        # Already-submitted target ids
        campaign_ids = [c.id for c in campaigns]
        submitted_target_ids = set(
            (
                await db.execute(
                    select(FeedbackResponse.target_id).where(
                        FeedbackResponse.campaign_id.in_(campaign_ids),
                        FeedbackResponse.student_id == student_id,
                    )
                )
            ).scalars().all()
        )

        # Load teacher names
        teachers = {
            u.id: u.name
            for u in (
                await db.execute(select(User).where(User.id.in_(student_teacher_ids)))
            ).scalars().all()
        }
        # Load subject names
        subject_ids = {r.subject_id for r in student_teachers}
        subjects = {
            s.id: s.name
            for s in (
                await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))
            ).scalars().all()
        } if subject_ids else {}
        classes = {
            c.id: c.name
            for c in (
                await db.execute(
                    select(SchoolClass).where(SchoolClass.id.in_(student_class_ids))
                )
            ).scalars().all()
        }

        result: list[StudentFeedbackCampaign] = []
        for campaign in campaigns:
            # All targets for this campaign
            all_targets = (
                await db.execute(
                    select(FeedbackCampaignTarget).where(
                        FeedbackCampaignTarget.campaign_id == campaign.id
                    )
                )
            ).scalars().all()

            # Filter to targets that involve this student's teachers, subjects and classes
            visible_targets: list[StudentFeedbackTarget] = []
            for t in all_targets:
                if t.teacher_id not in student_teacher_ids:
                    continue
                if t.class_id is not None and t.class_id not in student_class_ids:
                    continue
                if t.subject_id is not None and (t.teacher_id, t.subject_id) not in student_teacher_subject_pairs:
                    continue
                visible_targets.append(
                    StudentFeedbackTarget(
                        target_id=t.id,
                        teacher_id=t.teacher_id,
                        teacher_name=teachers.get(t.teacher_id),
                        subject_id=t.subject_id,
                        subject_name=subjects.get(t.subject_id) if t.subject_id else None,
                        class_name=classes.get(t.class_id) if t.class_id else None,
                        already_submitted=t.id in submitted_target_ids,
                    )
                )

            if visible_targets:
                result.append(
                    StudentFeedbackCampaign(
                        id=campaign.id,
                        title=campaign.title,
                        description=campaign.description,
                        starts_at=campaign.starts_at,
                        ends_at=campaign.ends_at,
                        targets=visible_targets,
                    )
                )

        return result

    @staticmethod
    async def submit_feedback(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        student_id: uuid.UUID,
        campaign_id: uuid.UUID,
        payload: FeedbackSubmit,
    ) -> None:
        """Submit (or check-duplicate) feedback from a student for one target."""
        now = datetime.now(timezone.utc)

        # Validate campaign is active and within window
        campaign = await FeedbackService._get_campaign_or_404(db, campaign_id, tenant_id)
        if campaign.status != CampaignStatus.ACTIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This feedback campaign is not active")
        if now < campaign.starts_at or now > campaign.ends_at:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Feedback window is not open")

        # Validate target belongs to campaign
        target = (
            await db.execute(
                select(FeedbackCampaignTarget).where(
                    FeedbackCampaignTarget.id == payload.target_id,
                    FeedbackCampaignTarget.campaign_id == campaign_id,
                )
            )
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Feedback target not found in this campaign")

        # Verify the student actually studies under this teacher
        # (prevent submitting for arbitrary teachers)
        student_class_ids = set(
            (
                await db.execute(
                    select(Enrollment.class_id).where(
                        Enrollment.student_id == student_id,
                        cast(Enrollment.status, String) == EnrollmentStatus.ACTIVE.value,
                    )
                )
            ).scalars().all()
        )
        teacher_match_clauses = [
            TeacherSubject.teacher_id == target.teacher_id,
            Subject.class_id.in_(student_class_ids),
        ]
        if target.subject_id is not None:
            teacher_match_clauses.append(TeacherSubject.subject_id == target.subject_id)
        if target.class_id is not None:
            teacher_match_clauses.append(Subject.class_id == target.class_id)

        teacher_subjects_match = (
            await db.execute(
                select(TeacherSubject.id)
                .join(Subject, TeacherSubject.subject_id == Subject.id)
                .where(and_(*teacher_match_clauses))
                .limit(1)
            )
        ).scalar_one_or_none()
        if teacher_subjects_match is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in a class taught by this teacher for this subject",
            )

        # Duplicate check (unique constraint also guards, but friendly error first)
        existing = (
            await db.execute(
                select(FeedbackResponse.id).where(
                    FeedbackResponse.campaign_id == campaign_id,
                    FeedbackResponse.target_id == payload.target_id,
                    FeedbackResponse.student_id == student_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="You have already submitted feedback for this teacher in this campaign",
            )

        response = FeedbackResponse(
            id=uuid.uuid4(),
            campaign_id=campaign_id,
            target_id=payload.target_id,
            student_id=student_id,
            teaching_clarity=payload.teaching_clarity,
            subject_knowledge=payload.subject_knowledge,
            interaction=payload.interaction,
            overall=payload.overall,
            comment=payload.comment,
        )
        db.add(response)
        await db.flush()
        await db.commit()

    # ── Teacher surface ───────────────────────────────────────────────────────

    @staticmethod
    async def get_teacher_feedback_results(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        teacher_id: uuid.UUID,
    ) -> list[TeacherFeedbackResult]:
        """Return aggregated feedback results for a teacher across all campaigns."""
        # Find targets that include this teacher
        targets = (
            await db.execute(
                select(FeedbackCampaignTarget)
                .join(
                    FeedbackCampaign,
                    FeedbackCampaignTarget.campaign_id == FeedbackCampaign.id,
                )
                .where(
                    FeedbackCampaignTarget.teacher_id == teacher_id,
                    FeedbackCampaign.tenant_id == tenant_id,
                    FeedbackCampaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.CLOSED]),
                )
            )
        ).scalars().all()

        if not targets:
            return []

        campaign_ids = list({t.campaign_id for t in targets})
        campaigns = {
            c.id: c
            for c in (
                await db.execute(
                    select(FeedbackCampaign).where(FeedbackCampaign.id.in_(campaign_ids))
                )
            ).scalars().all()
        }

        results: list[TeacherFeedbackResult] = []
        for campaign_id, campaign in campaigns.items():
            teacher_targets = [t for t in targets if t.campaign_id == campaign_id]
            t_ids = [t.id for t in teacher_targets]

            agg_rows = (
                await db.execute(
                    select(
                        func.count(FeedbackResponse.id).label("count"),
                        func.avg(FeedbackResponse.teaching_clarity).label("tc_avg"),
                        func.avg(FeedbackResponse.subject_knowledge).label("sk_avg"),
                        func.avg(FeedbackResponse.interaction).label("int_avg"),
                        func.avg(FeedbackResponse.overall).label("ov_avg"),
                    ).where(FeedbackResponse.target_id.in_(t_ids))
                )
            ).one()

            comments: list[str] | None = None
            if not campaign.allow_anonymous:
                comments = list(
                    (
                        await db.execute(
                            select(FeedbackResponse.comment).where(
                                FeedbackResponse.target_id.in_(t_ids),
                                FeedbackResponse.comment.is_not(None),
                                FeedbackResponse.comment != "",
                            )
                        )
                    ).scalars().all()
                )

            def _r(v) -> float | None:
                return round(float(v), 2) if v is not None else None

            results.append(
                TeacherFeedbackResult(
                    campaign_id=campaign.id,
                    campaign_title=campaign.title,
                    starts_at=campaign.starts_at,
                    ends_at=campaign.ends_at,
                    status=campaign.status.value if hasattr(campaign.status, "value") else campaign.status,
                    response_count=int(agg_rows.count or 0),
                    teaching_clarity_avg=_r(agg_rows.tc_avg),
                    subject_knowledge_avg=_r(agg_rows.sk_avg),
                    interaction_avg=_r(agg_rows.int_avg),
                    overall_avg=_r(agg_rows.ov_avg),
                    comments=comments,
                )
            )

        return results

    # ── Scheduler job — auto-close expired campaigns ──────────────────────────

    @staticmethod
    async def auto_close_expired_campaigns(db: AsyncSession) -> int:
        """Close ACTIVE campaigns whose ends_at has passed. Returns count closed."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(FeedbackCampaign)
            .where(
                FeedbackCampaign.status == CampaignStatus.ACTIVE,
                FeedbackCampaign.ends_at <= now,
            )
            .values(status=CampaignStatus.CLOSED, closed_at=now)
        )
        closed = result.rowcount or 0
        if closed:
            await db.commit()
            logger.info("Auto-closed %d expired feedback campaign(s)", closed)
        return int(closed)
