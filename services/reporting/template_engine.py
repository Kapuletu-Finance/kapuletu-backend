from datetime import datetime
import random
from common.utils import parse_uuid
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from models.campaign import Campaign
from models.transaction import Transaction
from models.report_settings import CampaignReportSettings
from common.config import get_config

class TemplateEngine:
    """
    TemplateEngine: Compiles dynamic, culturally formatted WhatsApp reports.
    Uses either the Default KapuLetu Standard or custom User Settings.
    """
    def __init__(self, db: Session):
        self.db = db

    def _generate_pin(self) -> str:
        return str(random.randint(1000, 9999))

    def get_or_create_settings(self, campaign_id: str) -> CampaignReportSettings:
        settings = self.db.execute(
            select(CampaignReportSettings).where(CampaignReportSettings.campaign_id == parse_uuid(campaign_id))
        ).scalars().first()
        
        if not settings:
            settings = CampaignReportSettings(
                campaign_id=campaign_id,
                public_access_pin=self._generate_pin()
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
            
        return settings

    def generate_whatsapp_report(self, campaign_id: str) -> str:
        # 1. Fetch Campaign and Data
        campaign = self.db.execute(select(Campaign).where(Campaign.campaign_id == parse_uuid(campaign_id))).scalars().first()
        if not campaign:
            return "ERROR: Campaign not found."

        settings = self.get_or_create_settings(campaign_id)
        
        txns = self.db.execute(
            select(Transaction).options(joinedload(Transaction.allocations)).where(
                Transaction.campaign_id == parse_uuid(campaign_id),
                Transaction.status == "approved"
            ).order_by(Transaction.created_at.asc())
        ).scalars().unique().all()

        # 2. Calculate Variables
        total_collected = sum(float(t.amount) for t in txns)
        target = float(campaign.target_amount) if campaign.target_amount else 0.0
        deficit = max(0, target - total_collected)
        
        from datetime import timezone
        import zoneinfo
        now_eat = datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
        date_str = now_eat.strftime("%A %d %B, %Y")

        # 3. Default KapuLetu Standard Templates
        default_header = (
            f"KAPULETU TREASURY UPDATE\n"
            f"*{campaign.title.upper()}*\n"
            f"As of {date_str}\n\n"
            f"Thank you for your continued support and contributions.\n\n"
            f"CONTRIBUTOR LIST:\n"
            f"------------------------------------"
        )
        
        default_footer = (
            f"------------------------------------\n"
            f"FINANCIAL SUMMARY:\n"
            f"Total Paid      = KSh. {total_collected:>10,.0f}\n"
            f"Expected Amount = KSh. {target:>10,.0f}\n"
            f"Deficit         = KSh. {deficit:>10,.0f}\n\n"
            f"{{payment_instructions}}\n"
            f"Thank you for your continued support."
        )

        header = settings.header_template or default_header
        footer = settings.footer_template or default_footer

        # Smart Tag Replacement
        pay_instruct = campaign.payment_instructions if campaign.payment_instructions else ""
        
        replacements = {
            "{{campaign_title}}": campaign.title,
            "{{current_date}}": date_str,
            "{{total_raised}}": f"{total_collected:,.0f}",
            "{{target_amount}}": f"{target:,.0f}",
            "{{deficit}}": f"{deficit:,.0f}",
            "{{payment_instructions}}": pay_instruct
        }
        
        for tag, val in replacements.items():
            header = header.replace(tag, str(val))
            footer = footer.replace(tag, str(val))

        # 4. Compile Contributor List
        report = header + "\n"
        
        counter = 1
        for t in txns:
            emoji = "✅" if settings.use_emojis else ""
            status_txt = "(paid)" if settings.show_status_text else ""
            
            if t.allocations:
                for alloc in t.allocations:
                    name = alloc.member_name or "Member"
                    amount = float(alloc.allocated_amount)
                    report += f"{counter}. {name} - {amount:,.0f} {status_txt}{emoji}\n"
                    counter += 1
            else:
                name = t.sender_name or (f"Member {t.sender_phone[-4:]}" if t.sender_phone else "Member")
                amount = float(t.amount)
                report += f"{counter}. {name} - {amount:,.0f} {status_txt}{emoji}\n"
                counter += 1

        # 5. Append Blank Slots (Who is next?)
        if settings.blank_slots_count > 0:
            report += "\n"
            for _ in range(settings.blank_slots_count):
                report += f"{counter}.\n"
                counter += 1

        report += "\n" + footer + "\n\n"

        # 6. Append Public Web Link CTA
        config = get_config()
        frontend_url = config.FRONTEND_URL.rstrip('/')
        group_id = campaign.group.slug or campaign.group_id
        camp_id = campaign.slug or campaign.campaign_id
        workspace_id = campaign.group.owner_id
        report += (
            f"====================================\n"
            f" View organized live report online:\n"
            f"{frontend_url}/report/w/{workspace_id}/g/{group_id}/c/{camp_id}\n"
            f"Access Code: {settings.public_access_pin}\n"
            f"===================================="
        )

        return report
