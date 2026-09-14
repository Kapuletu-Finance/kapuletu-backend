import csv
from io import StringIO
import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc
import openpyxl
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from models.subscription import Subscription, SubscriptionPayment, Plan
from models.users import User

class FinancialAnalyticsEngine:
    """
    Advanced financial analytics engine capable of calculating MRR,
    Revenue Flows, Churn rates, and generating exportable reports.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_health_metrics(self, start_date: datetime.datetime = None, end_date: datetime.datetime = None) -> Dict[str, Any]:
        """
        Generates point-in-time financial snapshots including MRR and active subscribers.
        """
        now = datetime.datetime.utcnow()
        if not end_date: end_date = now
        
        # Base query for all active subscriptions
        active_subs = self.db.query(Subscription).filter(
            Subscription.status == "active"
        ).all()
        
        # Subquery to check if user has paid
        paid_user_ids = {
            r[0] for r in self.db.query(SubscriptionPayment.user_id).filter(
                SubscriptionPayment.status == "success",
                SubscriptionPayment.amount > 0
            ).all()
        }
        
        total_active_subscribers = 0
        trial_subscribers = 0
        
        for sub in active_subs:
            # An active sub with an end date and no payments > 0 is considered a trial
            if sub.user_id in paid_user_ids:
                total_active_subscribers += 1
            else:
                # If they have no payments and it's active, it's a trial
                trial_subscribers += 1
        
        # Calculate MRR by summing the prices of PAID active subscriptions
        mrr = self.db.query(func.sum(Plan.price)).select_from(Subscription).join(
            Plan, Subscription.plan_id == Plan.plan_id
        ).filter(
            Subscription.status == "active",
            Subscription.user_id.in_(paid_user_ids) if paid_user_ids else False
        ).scalar() or 0

        # Calculate Churn Rate (simplified: expired subs in last 30 days / total subs)
        thirty_days_ago = now - datetime.timedelta(days=30)
        recently_expired = self.db.query(Subscription).filter(
            Subscription.status == "active", # Some may just have an end_date that passed
            Subscription.end_date != None,
            Subscription.end_date >= thirty_days_ago,
            Subscription.end_date <= now
        ).count()
        
        total_subs = total_active_subscribers + trial_subscribers + recently_expired
        churn_rate = (recently_expired / total_subs * 100) if total_subs > 0 else 0

        return {
            "mrr": mrr,
            "active_subscribers": total_active_subscribers,
            "trial_subscribers": trial_subscribers,
            "churn_rate_percent": round(churn_rate, 2),
            "generated_at": now.isoformat()
        }

    def get_revenue_flow(self, interval: str = "month", start_date: datetime.datetime = None) -> List[Dict[str, Any]]:
        """
        Groups revenue records over a time-series interval (week/month).
        """
        if not start_date:
            # Default to last 6 months
            start_date = datetime.datetime.utcnow() - datetime.timedelta(days=180)
            
        # Standardize grouping based on PostgreSQL / SQLite dialect 
        # PostgreSQL uses to_char
        group_format = 'YYYY-MM' if interval == 'month' else 'IYYY-IW'

        results = self.db.query(
            func.to_char(SubscriptionPayment.created_at, group_format).label("period"),
            Plan.name.label("plan_name"),
            func.sum(SubscriptionPayment.amount).label("revenue")
        ).join(
            Subscription, SubscriptionPayment.subscription_id == Subscription.subscription_id
        ).join(
            Plan, Subscription.plan_id == Plan.plan_id
        ).filter(
            SubscriptionPayment.created_at >= start_date,
            SubscriptionPayment.status == "success"
        ).group_by(
            "period", "plan_name"
        ).order_by("period").all()

        # Reshape data for Recharts stacked area chart
        # Target format: [{ period: "2023-01", "Basic": 0, "Silver": 500 }, ...]
        flow_data = {}
        for row in results:
            period = row.period
            plan = row.plan_name
            revenue = row.revenue
            if period not in flow_data:
                flow_data[period] = {"period": period}
            flow_data[period][plan] = revenue
            
        return list(flow_data.values())

    def generate_export(self, start_date: datetime.datetime = None, end_date: datetime.datetime = None, format: str = "csv") -> tuple[Any, str]:
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
            import io
            output = io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=letter)
            elements = []
            
            styles = getSampleStyleSheet()
            elements.append(Paragraph("Financial Export Report", styles['Title']))
            elements.append(Paragraph(f"Generated at: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
            
            # Prepare data for table
            data = [headers]
            for r in records:
                full_name = f"{r.first_name} {r.last_name}"
                data.append([
                    str(r.payment_id)[:8] + "...", # truncate UUID for PDF space
                    r.created_at.strftime("%Y-%m-%d"),
                    r.email[:15] + "..." if len(r.email) > 15 else r.email,
                    full_name[:15] + "..." if full_name else "",
                    r.plan_name,
                    str(r.amount),
                    r.currency,
                    r.payment_method,
                    r.status,
                ])
                
            t = Table(data, style=[
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ])
            elements.append(t)
            doc.build(elements)
            return output.getvalue(), "application/pdf"
            
        return "", "text/plain"

    def get_cohort_retention(self) -> List[Dict[str, Any]]:
        """
        Calculates user retention grouped by signup month (cohort).
        Returns a list of cohorts with their retention percentages over 12 months.
        """
        users = self.db.query(
            User.user_id,
            func.to_char(User.created_at, 'YYYY-MM').label("cohort")
        ).all()
        
        cohorts = {}
        for u in users:
            if u.cohort not in cohorts:
                cohorts[u.cohort] = {"total": 0, "users": []}
            cohorts[u.cohort]["total"] += 1
            cohorts[u.cohort]["users"].append(u.user_id)
            
        results = []
        now = datetime.datetime.utcnow()
        
        for cohort_month, data in sorted(cohorts.items(), reverse=True):
            retention = []
            cohort_date = datetime.datetime.strptime(cohort_month, "%Y-%m")
            
            for month_offset in range(12):
                check_date = cohort_date + datetime.timedelta(days=30 * month_offset)
                if check_date > now:
                    break
                    
                # To accurately check retention at month M, we check active subs in that window
                active_users = self.db.query(Subscription.user_id).filter(
                    Subscription.user_id.in_(data["users"]),
                    Subscription.status == "active",
                    Subscription.start_date <= check_date
                ).distinct().count()
                
                if month_offset == 0:
                    retention.append(100)
                else:
                    perc = int((active_users / data["total"]) * 100) if data["total"] > 0 else 0
                    retention.append(perc)
                    
            results.append({
                "cohort": cohort_month,
                "users": data["total"],
                "retention": retention
            })
            
        return results
