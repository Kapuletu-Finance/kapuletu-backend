import csv
from io import StringIO
import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc
import openpyxl

from models.subscription import Subscription, SubscriptionPayment, Plan
from models.users import User

class FinancialAnalyticsEngine:
    """
    Payment exports (CSV, Excel, official PDF). Metrics live in services/admin/finance/metrics.py.
    """
    def __init__(self, db: Session):
        self.db = db

    def _export_pdf(self, records, start_date, end_date, prepared_by, actor_id) -> bytes:
        """Financial export as an official Kapuletu document."""
        from services.documents.official import OfficialDocument

        period = " – ".join(
            d.strftime("%d %b %Y") for d in (start_date, end_date) if d
        ) or "All time"
        successful = [r for r in records if r.status == "success"]
        doc = OfficialDocument(
            self.db,
            title="Financial Transactions Export",
            subtitle=f"Subscription payments · {period}",
            department="FIN",
            doc_type="EXP",
            prepared_by=prepared_by,
            orientation="landscape",
        )
        doc.section("Summary")
        doc.key_figures([
            ("Payments", str(len(records)), "All statuses"),
            ("Successful", str(len(successful)), f"{len(records) - len(successful)} other"),
            ("Revenue collected", f"KES {sum(float(r.amount or 0) for r in successful):,.2f}", "Successful payments"),
            ("Period", period, None),
        ])
        doc.section("Payments")
        doc.table(
            ["Date", "Customer", "Email", "Plan", "Amount", "Currency", "Method", "Status", "Payment ID"],
            [
                [
                    r.created_at.strftime("%Y-%m-%d %H:%M"),
                    f"{r.first_name} {r.last_name}",
                    r.email,
                    r.plan_name,
                    f"{float(r.amount or 0):,.2f}",
                    r.currency,
                    r.payment_method or "—",
                    r.status,
                    str(r.payment_id)[:8],
                ]
                for r in records
            ],
            col_widths=[0.11, 0.14, 0.2, 0.1, 0.09, 0.07, 0.08, 0.09, 0.12],
            numeric_cols={4},
        )
        doc.signature_block()
        return doc.build(actor_id=actor_id, audit_details={"export": "subscription_payments", "period": period})

    def generate_export(
        self,
        start_date: datetime.datetime = None,
        end_date: datetime.datetime = None,
        format: str = "csv",
        prepared_by: str = None,
        actor_id: str = None,
    ) -> tuple[Any, str]:
        """
        Generates a robust financial export format ready for Excel/Pandas consumption.
        Returns a tuple of (file_data_bytes_or_string, mime_type)
        """
        query = self.db.query(
            SubscriptionPayment.payment_id,
            SubscriptionPayment.amount,
            SubscriptionPayment.currency,
            SubscriptionPayment.status,
            SubscriptionPayment.payment_method,
            SubscriptionPayment.created_at,
            User.email,
            User.first_name,
            User.last_name,
            Plan.name.label("plan_name")
        ).join(
            User, SubscriptionPayment.user_id == User.user_id
        ).join(
            Subscription, SubscriptionPayment.subscription_id == Subscription.subscription_id
        ).join(
            Plan, Subscription.plan_id == Plan.plan_id
        )

        if start_date:
            query = query.filter(SubscriptionPayment.created_at >= start_date)
        if end_date:
            query = query.filter(SubscriptionPayment.created_at <= end_date)

        query = query.order_by(desc(SubscriptionPayment.created_at))
        records = query.all()

        headers = ["Payment ID", "Date", "User Email", "User Name", "Plan Tier", "Amount", "Currency", "Method", "Status"]

        if format == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            
            for r in records:
                writer.writerow([
                    str(r.payment_id),
                    r.created_at.isoformat(),
                    r.email,
                    f"{r.first_name} {r.last_name}",
                    r.plan_name,
                    r.amount,
                    r.currency,
                    r.payment_method,
                    r.status,
                ])
            return output.getvalue(), "text/csv"
            
        elif format == "excel":
            import io
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Financial Records"
            
            ws.append(headers)
            for col in range(1, 10):
                ws.cell(row=1, column=col).font = openpyxl.styles.Font(bold=True)
                
            for r in records:
                ws.append([
                    str(r.payment_id),
                    r.created_at.strftime("%Y-%m-%d %H:%M"),
                    r.email,
                    f"{r.first_name} {r.last_name}",
                    r.plan_name,
                    float(r.amount) if r.amount else 0.0,
                    r.currency,
                    r.payment_method,
                    r.status,
                ])
                
            output = io.BytesIO()
            wb.save(output)
            return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
        elif format == "pdf":
            return self._export_pdf(records, start_date, end_date, prepared_by, actor_id), "application/pdf"
            
        return "", "text/plain"
