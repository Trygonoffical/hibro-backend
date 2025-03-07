from decimal import Decimal
import logging
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Q
from home.models import MLMMember, Commission, Order, Wallet, WalletTransaction, Notification

logger = logging.getLogger(__name__)

def calculate_monthly_commissions():
    """
    Calculate monthly commissions for all MLM members
    This should be run on the 1st of each month
    """
    try:
        # Get the first day of current month
        today = timezone.now()
        first_day_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get the first day of previous month
        if today.month == 1:
            first_day_prev_month = today.replace(year=today.year-1, month=12, day=1, 
                                              hour=0, minute=0, second=0, microsecond=0)
        else:
            first_day_prev_month = today.replace(month=today.month-1, day=1, 
                                              hour=0, minute=0, second=0, microsecond=0)
        
        # Get the last day of previous month
        last_day_prev_month = first_day_current_month - timezone.timedelta(microseconds=1)
        
        logger.info(f"Calculating commissions from {first_day_prev_month} to {last_day_prev_month}")
        
        # Calculate business (orders) for each MLM member in the previous month
        member_business = {}
        mlm_members = {}
        
        # Get all MLM members and index them by ID for fast lookup
        all_members = MLMMember.objects.select_related('user', 'position', 'sponsor')
        for member in all_members:
            mlm_members[member.id] = member
            
            # Get business (orders) for this member in the previous month
            orders = Order.objects.filter(
                user=member.user,
                order_date__gte=first_day_prev_month,
                order_date__lte=last_day_prev_month,
                status__in=['CONFIRMED', 'SHIPPED', 'DELIVERED']
            )
            
            # Calculate total business
            total_business = orders.aggregate(total=Sum('final_amount'))['total'] or Decimal('0.00')
            total_bp = orders.aggregate(total=Sum('total_bp'))['total'] or 0
            
            member_business[member.id] = {
                'total_business': total_business,
                'total_bp': total_bp,
                'member': member
            }
            
            logger.info(f"Member {member.member_id}: Business={total_business}, BP={total_bp}")
        
        # Check which members meet the monthly quota
        active_members = {}
        for member_id, data in member_business.items():
            member = data['member']
            
            # Skip if no position (shouldn't happen)
            if not member.position:
                continue
                
            # Check if member meets monthly quota
            meets_quota = data['total_business'] >= member.position.monthly_quota
            
            if meets_quota:
                active_members[member_id] = True
                logger.info(f"Member {member.member_id} meets monthly quota")
            else:
                active_members[member_id] = False
                logger.info(f"Member {member.member_id} does NOT meet monthly quota")
        
        # Create all commissions in a single transaction
        with transaction.atomic():
            commissions_created = 0
            bp_updates = []
            
            # Process each member that had business in the previous month
            for member_id, data in member_business.items():
                member = data['member']
                member_business_amount = data['total_business']
                member_bp = data['total_bp']
                
                # Skip if no business
                if member_business_amount <= 0:
                    continue
                
                # Find sponsor
                sponsor = member.sponsor
                
                if not sponsor:
                    # Skip if no sponsor or if sponsor would be inactive
                    continue
                
                # Process upline until we reach the top or max levels
                current_member = member
                current_sponsor = sponsor
                level = 1
                
                while current_sponsor and level <= 10:  # Limit to 10 levels max
                    # Skip if sponsor is inactive or doesn't meet quota
                    if not active_members.get(current_sponsor.id, False):
                        logger.info(f"Sponsor {current_sponsor.member_id} is inactive, skipping")
                        current_sponsor = current_sponsor.sponsor
                        level += 1
                        continue
                    
                    # Skip if sponsor can't earn commissions
                    if not current_sponsor.position or not current_sponsor.position.can_earn_commission:
                        logger.info(f"Sponsor {current_sponsor.member_id} cannot earn commission, skipping")
                        current_sponsor = current_sponsor.sponsor
                        level += 1
                        continue
                    
                    # Get position percentages
                    sponsor_percentage = current_sponsor.position.discount_percentage
                    member_percentage = current_member.position.discount_percentage
                    
                    # Calculate differential percentage
                    diff_percentage = sponsor_percentage - member_percentage
                    
                    # If sponsor's percentage is lower or equal, skip this level
                    if diff_percentage <= 0:
                        logger.info(f"No commission for {current_sponsor.member_id}: diff={diff_percentage}%")
                        current_sponsor = current_sponsor.sponsor
                        level += 1
                        continue
                    
                    # Calculate commission amount
                    commission_amount = (member_business_amount * diff_percentage) / 100
                    
                    if commission_amount > 0:
                        # Create commission record
                        commission = Commission(
                            member=current_sponsor,
                            from_member=member,
                            order=None,  # Monthly calculation has no specific order
                            amount=commission_amount,
                            level=level,
                            is_paid=True,  # Auto-paid for monthly calculations
                            payment_date=timezone.now(),
                            commission_type='MONTHLY',
                            calculation_month=first_day_prev_month,
                            details={
                                'member_position': member.position.name,
                                'member_percentage': float(member_percentage),
                                'sponsor_position': current_sponsor.position.name,
                                'sponsor_percentage': float(sponsor_percentage),
                                'diff_percentage': float(diff_percentage),
                                'business_amount': float(member_business_amount),
                                'calculation_period': {
                                    'from': first_day_prev_month.isoformat(),
                                    'to': last_day_prev_month.isoformat()
                                }
                            }
                        )
                        
                        commission.save()
                        commissions_created += 1
                        
                        logger.info(f"Created commission: {current_sponsor.member_id} <- {member.member_id}: {commission_amount}")
                        
                        # Create wallet transaction
                        wallet, created = Wallet.objects.get_or_create(user=current_sponsor.user)
                        wallet.balance += commission_amount
                        wallet.save()
                        
                        WalletTransaction.objects.create(
                            wallet=wallet,
                            amount=commission_amount,
                            transaction_type='COMMISSION',
                            description=f"Monthly commission from {member.user.get_full_name() or member.member_id}",
                            reference_id=str(commission.id)
                        )
                        
                        # Create notification
                        Notification.objects.create(
                            title="Monthly Commission Received",
                            message=f"You have received a commission of ₹{commission_amount} from {member.user.get_full_name() or member.member_id}'s business for {first_day_prev_month.strftime('%B %Y')}.",
                            notification_type='INDIVIDUAL',
                            recipient=current_sponsor
                        )
                    
                    # Transfer BP points from downline to sponsor
                    if member_bp > 0:
                        bp_updates.append({
                            'sponsor': current_sponsor,
                            'bp_to_add': member_bp
                        })
                    
                    # Move up to next level
                    current_member = current_sponsor
                    current_sponsor = current_sponsor.sponsor
                    level += 1
            
            # Apply BP updates
            for update in bp_updates:
                sponsor = update['sponsor']
                bp_to_add = update['bp_to_add']
                
                sponsor.total_bp += bp_to_add
                sponsor.save()
                
                logger.info(f"Added {bp_to_add} BP to {sponsor.member_id}")
                
                # Check for position upgrade
                sponsor.check_position_upgrade()
        
        logger.info(f"Monthly commission calculation complete. Created {commissions_created} commissions.")
        return True
    
    except Exception as e:
        logger.error(f"Error in monthly commission calculation: {str(e)}")
        return False