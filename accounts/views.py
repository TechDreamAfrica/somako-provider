from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.views import View
from django.contrib.auth.views import LoginView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.utils import timezone
from django.conf import settings
from django.db import models
import logging
from .forms import CustomUserCreationForm, RoleApplicationForm
from .models import User, RoleApplication, VerificationCode
from utils.sms_utils import send_user_verification_code
from utils.email_utils import (
    send_welcome_email, 
    send_password_reset_email,
    send_login_notification_email,
    send_password_changed_email
)

logger = logging.getLogger(__name__)

def get_client_ip(request):
    """Get the client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def send_password_change_notification(user, request):
    """Send notification email when password is changed - wrapper for new utility function"""
    try:
        send_password_changed_email(user, request)
        logger.info(f"Password change notification sent to {user.email}")
    except Exception as e:
        logger.error(f"Error sending password change notification: {str(e)}")


def get_pwa_redirect_url(request, redirect_to='dashboard'):
    """
    Determine which PWA page to redirect to based on request context

    Args:
        request: HTTP request object
        redirect_to: 'dashboard' or 'login' - where to redirect after action

    Returns:
        URL name string for redirect
    """
    # Check referrer or session for PWA app context
    referrer = request.META.get('HTTP_REFERER', '')
    app_param = request.GET.get('app', '')
    session_app = request.session.get('source_pwa_app', '')

    pwa_app = None

    # Priority: URL param > session > referrer > default
    if app_param in ['food', 'ride', 'shop', 'pharmacy', 'rent', 'express']:
        request.session['source_pwa_app'] = app_param
        pwa_app = app_param
    elif session_app in ['food', 'ride', 'shop', 'pharmacy', 'rent', 'express']:
        pwa_app = session_app
    else:
        # Check referrer path
        if '/pwa/food/' in referrer:
            pwa_app = 'food'
        elif '/pwa/ride/' in referrer:
            pwa_app = 'ride'
        elif '/pwa/shop/' in referrer:
            pwa_app = 'shop'
        elif '/pwa/pharmacy/' in referrer:
            pwa_app = 'pharmacy'
        elif '/pwa/rent/' in referrer:
            pwa_app = 'rent'
        elif '/pwa/express/' in referrer:
            pwa_app = 'express'
        else:
            # Default to food PWA
            pwa_app = 'food'

        if pwa_app:
            request.session['source_pwa_app'] = pwa_app

    # Return appropriate URL based on redirect_to parameter
    if redirect_to == 'login':
        # For password reset, redirect to PWA login with app parameter
        return f'accounts:pwa_login'
    else:
        # For other actions, redirect to PWA dashboard
        return f'{pwa_app}_pwa:dashboard'


def signup_services_view(request):
    """View to display service selection page"""
    return render(request, 'accounts/signup_services.html')

class SignUpView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'accounts/signup.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass service and role from query params
        context['service'] = self.request.GET.get('service', '')
        context['role'] = self.request.GET.get('role', '')
        return context

    def form_valid(self, form):
        user = form.save(commit=False)

        # Get service role from query parameters
        self.request.GET.get('service', 'general')
        role = self.request.GET.get('role', 'general')

        # Map roles to service_roles field
        role_mapping = {
            'landlord': 'landlord',
            'seller': 'seller',
            'pharmacy_owner': 'pharmacy_owner',
            'restaurant_owner': 'restaurant_owner',
            'driver': 'driver',
            'rider': 'rider',
            'general': 'general',
        }

        user.service_roles = role_mapping.get(role, 'general')
        user.save()

        # Send welcome email
        try:
            send_welcome_email(user)
            messages.success(self.request, 'Account created successfully! Please check your email for welcome instructions.')
        except Exception as e:
            logger.error(f"Error sending welcome email: {str(e)}")
            messages.success(self.request, 'Account created successfully!')
            messages.info(self.request, 'We could not send a welcome email, but your account is ready to use.')

        login(self.request, user)
        return redirect('accounts:dashboard')

    def get_success_url(self):
        return reverse_lazy('accounts:dashboard')

class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'

    def form_valid(self, form):
        """Override to send login notification email"""
        response = super().form_valid(form)
        
        # Send login notification email if enabled
        if getattr(settings, 'SEND_LOGIN_NOTIFICATION_EMAIL', False):
            try:
                send_login_notification_email(self.request.user, self.request)
            except Exception as e:
                logger.error(f"Error sending login notification email: {str(e)}")
        
        return response

    def get_success_url(self):
        # Check if user has a driver profile and redirect to driver dashboard
        try:
            from ride.models import DriverProfile
            driver_profile = DriverProfile.objects.filter(user=self.request.user).first()
            if driver_profile:
                return reverse_lazy('ride:driver_dashboard')
        except Exception as e:
            logger.error(f"Error checking driver profile for user {self.request.user.username}: {str(e)}")
        
        # Default redirect to regular dashboard
        return reverse_lazy('accounts:dashboard')

@login_required
def profile_view(request):
    """Simplified profile view - only basic info and password"""
    user = request.user

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        logger.info(f"Profile form submission from user {user.username}, form_type: {form_type}")
        
        # Log all POST data for debugging (excluding sensitive info)
        post_data = {k: v for k, v in request.POST.items() if k not in ['csrfmiddlewaretoken']}
        logger.debug(f"POST data for user {user.username}: {post_data}")
        
        if form_type == 'basic':
            # Handle basic information form
            try:
                # Validate required fields
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                email = request.POST.get('email', '').strip()
                
                if not first_name or not last_name or not email:
                    messages.error(request, 'First name, last name, and email are required.')
                    return redirect('accounts:profile')
                
                # Validate email format
                import re
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, email):
                    messages.error(request, 'Please enter a valid email address.')
                    return redirect('accounts:profile')
                
                # Check if email is already taken by another user
                if User.objects.filter(email=email).exclude(id=user.id).exists():
                    messages.error(request, 'This email address is already registered to another account.')
                    return redirect('accounts:profile')
                
                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.phone_number = request.POST.get('phone_number', '').strip()
                user.location = request.POST.get('location', '').strip()
                user.bio = request.POST.get('bio', '').strip()
                
                # Handle profile picture upload with validation
                if 'profile_picture' in request.FILES:
                    profile_pic = request.FILES['profile_picture']
                    
                    # Validate file size (5MB limit)
                    if profile_pic.size > 5 * 1024 * 1024:  # 5MB in bytes
                        messages.error(request, 'Profile picture must be less than 5MB.')
                        return redirect('accounts:profile')
                    
                    # Validate file type
                    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
                    if profile_pic.content_type not in allowed_types:
                        messages.error(request, 'Profile picture must be a JPEG, PNG, or GIF image.')
                        return redirect('accounts:profile')
                    
                    # Delete old profile picture if it exists
                    if user.profile_picture:
                        try:
                            user.profile_picture.delete(save=False)
                        except:
                            pass  # Ignore errors if file doesn't exist
                    
                    user.profile_picture = profile_pic
                    messages.success(request, 'Profile picture updated successfully!')
                
                user.save()
                messages.success(request, 'Basic information updated successfully!')
                logger.info(f"User {user.username} updated basic profile information")
                
            except Exception as e:
                logger.error(f"Error updating basic information for user {user.username}: {str(e)}")
                messages.error(request, f'Error updating basic information: {str(e)}')
            
        elif form_type == 'professional':
            # Handle professional information form
            try:
                from core.models import Skill
                from .models import WorkerProfile
                
                # Get or create worker profile
                worker_profile, created = WorkerProfile.objects.get_or_create(user=user)
                
                # Update profile fields
                worker_profile.profession = request.POST.get('profession', '').strip()
                worker_profile.portfolio = request.POST.get('portfolio', '').strip()
                worker_profile.experience_level = request.POST.get('experience_level', 'entry')
                worker_profile.availability_type = request.POST.get('availability_type', 'freelance')
                worker_profile.languages = request.POST.get('languages', '').strip()
                worker_profile.previous_work = request.POST.get('previous_work', '').strip()
                worker_profile.education = request.POST.get('education', '').strip()
                worker_profile.certifications = request.POST.get('certifications', '').strip()
                
                # Handle resume upload with validation
                if 'resume' in request.FILES:
                    resume_file = request.FILES['resume']
                    
                    # Validate file size (5MB limit)
                    if resume_file.size > 5 * 1024 * 1024:  # 5MB
                        messages.error(request, 'Resume file must be less than 5MB.')
                        return redirect('accounts:profile')
                    
                    # Validate file type
                    allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
                    if resume_file.content_type not in allowed_types:
                        messages.error(request, 'Resume must be a PDF, DOC, or DOCX file.')
                        return redirect('accounts:profile')
                    
                    # Delete old resume if it exists
                    if worker_profile.resume:
                        try:
                            worker_profile.resume.delete(save=False)
                        except:
                            pass  # Ignore errors if file doesn't exist
                    
                    worker_profile.resume = resume_file
                
                # Handle numeric fields with proper validation
                experience_years = request.POST.get('experience_years', '').strip()
                if experience_years:
                    try:
                        years = int(experience_years)
                        if 0 <= years <= 50:
                            worker_profile.experience_years = years
                        else:
                            messages.warning(request, 'Experience years must be between 0 and 50.')
                            worker_profile.experience_years = 0
                    except ValueError:
                        messages.warning(request, 'Invalid experience years value.')
                        worker_profile.experience_years = 0
                else:
                    worker_profile.experience_years = 0
                
                # Handle hourly rate
                hourly_rate = request.POST.get('hourly_rate', '').strip()
                if hourly_rate:
                    try:
                        rate = float(hourly_rate)
                        if 5 <= rate <= 1000:
                            worker_profile.hourly_rate = rate
                        else:
                            messages.warning(request, 'Hourly rate must be between $5 and $1000.')
                            worker_profile.hourly_rate = None
                    except ValueError:
                        messages.warning(request, 'Invalid hourly rate value.')
                        worker_profile.hourly_rate = None
                else:
                    worker_profile.hourly_rate = None
                
                # Handle minimum project budget
                minimum_project_budget = request.POST.get('minimum_project_budget', '').strip()
                if minimum_project_budget:
                    try:
                        budget = float(minimum_project_budget)
                        if 10 <= budget <= 100000:
                            worker_profile.minimum_project_budget = budget
                        else:
                            messages.warning(request, 'Project budget must be between $10 and $100,000.')
                            worker_profile.minimum_project_budget = None
                    except ValueError:
                        messages.warning(request, 'Invalid project budget value.')
                        worker_profile.minimum_project_budget = None
                else:
                    worker_profile.minimum_project_budget = None
                
                # Handle boolean and text fields
                worker_profile.availability = 'availability' in request.POST
                worker_profile.availability_hours = request.POST.get('availability_hours', '').strip()
                
                worker_profile.save()
                
                # Handle skills - clear existing and add selected ones
                selected_skills = request.POST.getlist('skills')
                if selected_skills:
                    try:
                        # Validate that all selected skills exist
                        skills = Skill.objects.filter(id__in=selected_skills)
                        if skills.count() != len(selected_skills):
                            messages.warning(request, 'Some selected skills were not found.')
                        worker_profile.skills.set(skills)
                    except Exception as e:
                        logger.error(f"Error updating skills for user {user.username}: {str(e)}")
                        messages.warning(request, f'Error updating skills: {str(e)}')
                else:
                    worker_profile.skills.clear()
                
                messages.success(request, 'Professional information updated successfully!')
                logger.info(f"Worker {user.username} updated professional profile information")
                
            except Exception as e:
                logger.error(f"Error updating professional information for user {user.username}: {str(e)}")
                messages.error(request, f'Error updating professional information: {str(e)}')
        
        elif form_type == 'certification':
            # Handle certification form
            try:
                from .models import WorkerProfile, WorkerCertification
                from .forms import WorkerCertificationForm
                
                # Get or create worker profile
                worker_profile, created = WorkerProfile.objects.get_or_create(user=user)
                
                # Create form instance with POST data
                form = WorkerCertificationForm(request.POST, request.FILES)
                
                if form.is_valid():
                    certification = form.save(commit=False)
                    certification.worker_profile = worker_profile
                    certification.save()
                    messages.success(request, 'Certification added successfully!')
                else:
                    for field, errors in form.errors.items():
                        for error in errors:
                            messages.error(request, f'{field.title()}: {error}')
            except Exception as e:
                messages.error(request, f'Error adding certification: {str(e)}')
        
        elif form_type == 'education':
            # Handle education form
            try:
                from .models import WorkerProfile, WorkerEducation
                from .forms import WorkerEducationForm
                
                # Get or create worker profile
                worker_profile, created = WorkerProfile.objects.get_or_create(user=user)
                
                # Create form instance with POST data
                form = WorkerEducationForm(request.POST)
                
                if form.is_valid():
                    education = form.save(commit=False)
                    education.worker_profile = worker_profile
                    education.save()
                    messages.success(request, 'Education record added successfully!')
                else:
                    for field, errors in form.errors.items():
                        for error in errors:
                            messages.error(request, f'{field.title()}: {error}')
            except Exception as e:
                messages.error(request, f'Error adding education record: {str(e)}')
            
        elif form_type == 'portfolio':
            # Handle portfolio item creation with all fields
            try:
                from core.models import PortfolioItem
                from .models import WorkerProfile
                from datetime import datetime

                title = request.POST.get('title', '').strip()
                description = request.POST.get('description', '').strip()

                if title and description and 'image' in request.FILES:
                    # Get or create worker profile
                    worker_profile, created = WorkerProfile.objects.get_or_create(user=user)

                    # Validate file size (5MB limit)
                    portfolio_image = request.FILES['image']
                    if portfolio_image.size > 5 * 1024 * 1024:
                        messages.error(request, 'Portfolio image must be less than 5MB.')
                    else:
                        # Parse completion date
                        completion_date = request.POST.get('completion_date')
                        if completion_date:
                            try:
                                completion_date = datetime.strptime(completion_date, '%Y-%m-%d').date()
                            except:
                                completion_date = None
                        else:
                            completion_date = None

                        # Parse duration
                        duration_days = request.POST.get('duration_days')
                        try:
                            duration_days = int(duration_days) if duration_days else None
                        except:
                            duration_days = None

                        # Create portfolio item
                        portfolio_item = PortfolioItem.objects.create(
                            worker_profile=worker_profile,
                            title=title,
                            description=description,
                            image=portfolio_image,
                            project_type=request.POST.get('project_type', 'other'),
                            project_url=request.POST.get('project_url', '').strip(),
                            client_name=request.POST.get('client_name', '').strip(),
                            completion_date=completion_date,
                            duration_days=duration_days,
                            budget_range=request.POST.get('budget_range', '').strip(),
                            technologies=request.POST.get('technologies', '').strip(),
                            is_featured='is_featured' in request.POST,
                            is_public='is_public' in request.POST
                        )
                        messages.success(request, 'Portfolio item added successfully!')
                else:
                    messages.error(request, 'Please provide a title, description, and image for the portfolio item.')
            except Exception as e:
                logger.error(f"Error adding portfolio item: {str(e)}")
                messages.error(request, f'Error adding portfolio item: {str(e)}')
                
        elif form_type == 'edit_portfolio':
            # Handle portfolio item editing
            try:
                from core.models import PortfolioItem
                from datetime import datetime

                portfolio_id = request.POST.get('portfolio_id')
                portfolio_item = PortfolioItem.objects.get(
                    id=portfolio_id,
                    worker_profile__user=user
                )

                # Update fields
                portfolio_item.title = request.POST.get('title', '').strip()
                portfolio_item.description = request.POST.get('description', '').strip()
                portfolio_item.project_type = request.POST.get('project_type', 'other')
                portfolio_item.project_url = request.POST.get('project_url', '').strip()
                portfolio_item.client_name = request.POST.get('client_name', '').strip()
                portfolio_item.budget_range = request.POST.get('budget_range', '').strip()
                portfolio_item.technologies = request.POST.get('technologies', '').strip()
                portfolio_item.is_featured = 'is_featured' in request.POST
                portfolio_item.is_public = 'is_public' in request.POST

                # Parse completion date
                completion_date = request.POST.get('completion_date')
                if completion_date:
                    try:
                        portfolio_item.completion_date = datetime.strptime(completion_date, '%Y-%m-%d').date()
                    except:
                        portfolio_item.completion_date = None
                else:
                    portfolio_item.completion_date = None

                # Parse duration
                duration_days = request.POST.get('duration_days')
                try:
                    portfolio_item.duration_days = int(duration_days) if duration_days else None
                except:
                    portfolio_item.duration_days = None

                # Update image if provided
                if 'image' in request.FILES:
                    portfolio_image = request.FILES['image']
                    if portfolio_image.size > 5 * 1024 * 1024:
                        messages.error(request, 'Portfolio image must be less than 5MB.')
                        return redirect('accounts:profile')
                    portfolio_item.image = portfolio_image

                portfolio_item.save()
                messages.success(request, 'Portfolio item updated successfully!')
            except PortfolioItem.DoesNotExist:
                messages.error(request, 'Portfolio item not found.')
            except Exception as e:
                logger.error(f"Error updating portfolio item: {str(e)}")
                messages.error(request, f'Error updating portfolio item: {str(e)}')

        elif form_type == 'delete_portfolio':
            # Handle portfolio item deletion
            from core.models import PortfolioItem

            portfolio_id = request.POST.get('portfolio_id')
            try:
                portfolio_item = PortfolioItem.objects.get(
                    id=portfolio_id,
                    worker_profile__user=user
                )
                portfolio_item.delete()
                messages.success(request, 'Portfolio item deleted successfully!')
            except PortfolioItem.DoesNotExist:
                messages.error(request, 'Portfolio item not found.')

        elif form_type == 'delete_certification':
            # Handle certification deletion
            from .models import WorkerCertification
            
            certification_id = request.POST.get('certification_id')
            try:
                certification = WorkerCertification.objects.get(
                    id=certification_id,
                    worker_profile__user=user
                )
                certification.delete()
                messages.success(request, 'Certification deleted successfully!')
            except WorkerCertification.DoesNotExist:
                messages.error(request, 'Certification not found.')
                
        elif form_type == 'delete_education':
            # Handle education record deletion
            from .models import WorkerEducation
            
            education_id = request.POST.get('education_id')
            try:
                education = WorkerEducation.objects.get(
                    id=education_id,
                    worker_profile__user=user
                )
                education.delete()
                messages.success(request, 'Education record deleted successfully!')
            except WorkerEducation.DoesNotExist:
                messages.error(request, 'Education record not found.')
                
        elif form_type == 'password':
            # Handle password change
            from django.contrib.auth import update_session_auth_hash
            from django.contrib.auth.hashers import check_password
            
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if not check_password(current_password, user.password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'New password must be at least 8 characters long.')
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)  # Keep user logged in
                
                # Send password change notification email
                try:
                    send_password_change_notification(user, request)
                    messages.success(request, 'Password updated successfully! A confirmation email has been sent.')
                except Exception as e:
                    logger.error(f"Failed to send password change notification: {str(e)}")
                    messages.success(request, 'Password updated successfully!')
                    messages.info(request, 'We could not send a confirmation email, but your password has been changed.')
                
        elif form_type == 'settings':
            # Handle account settings
            user.email_notifications = 'email_notifications' in request.POST
            user.profile_visibility = 'profile_visibility' in request.POST
            user.save()
            messages.success(request, 'Account settings updated successfully!')
            
        elif form_type == 'deactivate':
            # Handle account deactivation
            user.is_active = False
            user.save()
            messages.info(request, 'Your account has been deactivated.')
            return redirect('accounts:login')
            
        elif form_type == 'delete':
            # Handle account deletion
            user.delete()
            messages.info(request, 'Your account has been permanently deleted.')
            return redirect('core:home')
        
        return redirect('accounts:profile')
    
    # GET request - display the profile form
    context = {
        'user': user,
    }
    
    # Note: legacy worker profile block removed (unused)
    return render(request, 'accounts/profile.html', context)

@login_required
def dashboard_view(request):
    user = request.user
    
    # Check if user has a driver profile and redirect to driver dashboard
    try:
        from ride.models import DriverProfile
        driver_profile = DriverProfile.objects.filter(user=user).first()
        if driver_profile:
            return redirect('ride:driver_dashboard')
    except Exception as e:
        logger.error(f"Error checking driver profile for user {user.username}: {str(e)}")
    
    context = {
        'user': user,
    }

    # Subscription CTA for providers without an active subscription (no import side-effects)
    subscription = getattr(user, 'subscription', None)
    has_active_subscription = subscription.is_active() if subscription else False
    is_provider = user.is_provider() if hasattr(user, 'is_provider') else False
    context['show_subscription_cta'] = bool(is_provider and not has_active_subscription)
    context['subscription'] = subscription

    # Choose a preferred service role with provider/customer precedence instead of naive first
    if hasattr(user, 'get_roles_list'):
        roles = user.get_roles_list()
        provider_priority = ['restaurant_owner', 'pharmacy_owner', 'seller', 'landlord', 'equipment_owner', 'driver']
        customer_priority = ['customer', 'patient', 'buyer', 'tenant', 'equipment_renter', 'rider']
        # Pick first matching provider role, else first matching customer role, else fallback
        service_role = next((r for r in provider_priority if r in roles), None)
        if not service_role:
            service_role = next((r for r in customer_priority if r in roles), None)
        service_role = service_role or (roles[0] if roles else 'general')
    else:
        service_role = 'general'
    context['service_role'] = service_role

    # Add service-specific data based on user's role
    if service_role == 'landlord':
        from rent.models import Property, RentalBooking
        properties = Property.objects.filter(owner=user)
        context['my_properties'] = properties.order_by('-created_at')[:5]
        context['properties_count'] = properties.count()
        context['active_bookings'] = RentalBooking.objects.filter(property__owner=user, status='active').count()
        context['pending_bookings'] = RentalBooking.objects.filter(property__owner=user, status='pending').count()
        context['total_bookings'] = RentalBooking.objects.filter(property__owner=user).count()
        context['service_name'] = 'Rent - Landlord'

    elif service_role == 'tenant':
        from rent.models import RentalBooking
        try:
            bookings = RentalBooking.objects.filter(renter=user)
            context['my_bookings'] = bookings.order_by('-created_at')[:5]
            context['active_bookings'] = bookings.filter(status='active').count()
            context['pending_bookings'] = bookings.filter(status='pending').count()
            context['completed_bookings'] = bookings.filter(status='completed').count()
            context['total_bookings'] = bookings.count()
        except Exception as e:
            logger.debug(f"Error fetching tenant bookings: {e}")
            context['my_bookings'] = []
        context['service_name'] = 'Rent - Tenant'

    elif service_role == 'seller':
        from shop.models import Product, Order
        products = Product.objects.filter(seller=user)
        context['my_products'] = products.order_by('-created_at')[:5]
        context['products_count'] = products.count()
        context['pending_orders'] = Order.objects.filter(product__seller=user, status='pending').count()
        context['completed_orders'] = Order.objects.filter(product__seller=user, status='completed').count()
        context['total_orders'] = Order.objects.filter(product__seller=user).count()
        context['service_name'] = 'Shop - Seller'

    elif service_role == 'buyer':
        from shop.models import Order
        try:
            orders = Order.objects.filter(customer=user)
            context['my_orders'] = orders.order_by('-created_at')[:5]
            context['pending_orders'] = orders.filter(status='pending').count()
            context['completed_orders'] = orders.filter(status='completed').count()
            context['cancelled_orders'] = orders.filter(status='cancelled').count()
            context['total_orders'] = orders.count()
        except Exception as e:
            logger.debug(f"Error fetching buyer orders: {e}")
            context['my_orders'] = []
        context['service_name'] = 'Shop - Buyer'

    elif service_role == 'pharmacy_owner':
        from pharmacy.models import Medicine, Order
        medicines = Medicine.objects.filter(pharmacy__owner=user)
        context['my_medicines'] = medicines.order_by('-created_at')[:5]
        context['medicines_count'] = medicines.count()
        context['pending_orders'] = Order.objects.filter(medicine__pharmacy__owner=user, status='pending').count()
        context['completed_orders'] = Order.objects.filter(medicine__pharmacy__owner=user, status='completed').count()
        context['total_orders'] = Order.objects.filter(medicine__pharmacy__owner=user).count()
        context['service_name'] = 'Pharmacy - Owner'

    elif service_role == 'patient':
        from pharmacy.models import Order
        try:
            orders = Order.objects.filter(customer=user)
            context['my_orders'] = orders.order_by('-created_at')[:5]
            context['pending_orders'] = orders.filter(status='pending').count()
            context['completed_orders'] = orders.filter(status='completed').count()
            context['cancelled_orders'] = orders.filter(status='cancelled').count()
            context['total_orders'] = orders.count()
        except Exception as e:
            logger.debug(f"Error fetching patient orders: {e}")
            context['my_orders'] = []
        context['service_name'] = 'Pharmacy - Patient'

    elif service_role == 'restaurant_owner':
        from django.db.models import Sum
        from food.models import Restaurant, Order, MenuItem
        restaurants = Restaurant.objects.filter(owner=user)
        context['my_restaurants'] = restaurants.order_by('-created_at')[:5]
        context['restaurants_count'] = restaurants.count()
        # Orders overview
        context['pending_orders'] = Order.objects.filter(restaurant__owner=user, status='pending').count()
        context['confirmed_orders'] = Order.objects.filter(restaurant__owner=user, status='confirmed').count()
        context['preparing_orders'] = Order.objects.filter(restaurant__owner=user, status='preparing').count()
        context['delivered_orders'] = Order.objects.filter(restaurant__owner=user, status='delivered').count()
        context['total_orders'] = Order.objects.filter(restaurant__owner=user).count()

        # Menu items count
        context['menu_items_count'] = MenuItem.objects.filter(restaurant__owner=user).count()

        # Revenue: sum of delivered orders (optionally paid)
        delivered_qs = Order.objects.filter(restaurant__owner=user, status='delivered')
        delivered_revenue = delivered_qs.aggregate(total=Sum('total_amount')).get('total') or 0
        context['delivered_revenue'] = delivered_revenue

        # Monthly revenue (last 30 days, delivered)
        from django.utils import timezone
        from datetime import timedelta
        start_30 = timezone.now() - timedelta(days=30)
        monthly_revenue = delivered_qs.filter(created_at__gte=start_30).aggregate(total=Sum('total_amount')).get('total') or 0
        context['monthly_revenue'] = monthly_revenue

        # Today's revenue (delivered orders today)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_revenue = delivered_qs.filter(created_at__gte=today_start).aggregate(total=Sum('total_amount')).get('total') or 0
        context['today_revenue'] = today_revenue
        context['service_name'] = 'Food - Restaurant Owner'

    elif service_role == 'customer':
        from food.models import Order
        try:
            orders = Order.objects.filter(customer=user)
            context['my_orders'] = orders.order_by('-created_at')[:5]
            context['pending_orders'] = orders.filter(status='pending').count()
            context['completed_orders'] = orders.filter(status='completed').count()
            context['cancelled_orders'] = orders.filter(status='cancelled').count()
            context['total_orders'] = orders.count()
        except Exception as e:
            logger.debug(f"Error fetching food orders: {e}")
            context['my_orders'] = []
        context['service_name'] = 'Food - Customer'

    elif service_role == 'driver':
        from ride.models import Ride
        try:
            rides = Ride.objects.filter(driver=user)
            context['my_rides'] = rides.order_by('-created_at')[:5]
            context['pending_rides'] = rides.filter(status='pending').count()
            context['active_rides'] = rides.filter(status='active').count()
            context['completed_rides'] = rides.filter(status='completed').count()
            context['total_rides'] = rides.count()
        except Exception as e:
            logger.debug(f"Error fetching driver rides: {e}")
            context['my_rides'] = []
        context['service_name'] = 'Ride - Driver'

    elif service_role == 'rider':
        from ride.models import Ride
        try:
            bookings = Ride.objects.filter(passenger=user)
            context['my_bookings'] = bookings.order_by('-requested_at')[:5]
            context['pending_rides'] = bookings.filter(status='REQUESTED').count()
            context['active_rides'] = bookings.filter(status__in=['ACCEPTED', 'DRIVER_ARRIVED', 'IN_PROGRESS']).count()
            context['completed_rides'] = bookings.filter(status='COMPLETED').count()
            context['total_rides'] = bookings.count()
        except Exception as e:
            logger.debug(f"Error fetching rider bookings: {e}")
            context['my_bookings'] = []
        context['service_name'] = 'Ride - Rider'

    else:
        # General user - fetch all activities across all apps
        context['service_name'] = 'General User'
        activities = []

        # Initialize counters
        rent_count = 0
        ride_count = 0
        food_count = 0
        shop_count = 0
        pharmacy_count = 0

        # Fetch Rent activities
        try:
            from rent.models import RentalBooking
            rent_bookings = RentalBooking.objects.filter(renter=user).select_related('property').order_by('-created_at')[:5]
            rent_count = RentalBooking.objects.filter(renter=user).count()
            for booking in rent_bookings:
                activities.append({
                    'type': 'rent_booking',
                    'icon': 'fa-home',
                    'title': f'Booked: {booking.property.title}',
                    'date': booking.created_at,
                    'url': f'/rent/bookings/{booking.id}/',
                    'status': booking.status
                })
        except Exception as e:
            logger.debug(f"Could not fetch rent bookings: {e}")

        # Fetch Ride activities
        try:
            from ride.models import Ride
            rides = Ride.objects.filter(passenger=user).select_related('driver').order_by('-requested_at')[:5]
            ride_count = Ride.objects.filter(passenger=user).count()
            for ride in rides:
                activities.append({
                    'type': 'ride',
                    'icon': 'fa-car',
                    'title': f'Ride from {ride.pickup_address} to {ride.dropoff_address}',
                    'date': ride.requested_at,
                    'url': f'/ride/ride/{ride.ride_id}/',
                    'status': ride.status
                })
        except Exception as e:
            logger.debug(f"Could not fetch rides: {e}")

        # Fetch Food orders
        try:
            from food.models import Order
            food_orders = Order.objects.filter(customer=user).select_related('restaurant').order_by('-created_at')[:5]
            food_count = Order.objects.filter(customer=user).count()
            for order in food_orders:
                activities.append({
                    'type': 'food_order',
                    'icon': 'fa-utensils',
                    'title': f'Order from {order.restaurant.name}',
                    'date': order.created_at,
                    'url': f'/food/orders/{order.order_number}/',
                    'status': order.status
                })
        except Exception as e:
            logger.debug(f"Could not fetch food orders: {e}")

        # Fetch Shop orders
        try:
            from shop.models import Order
            shop_orders = Order.objects.filter(user=user).order_by('-created_at')[:5]
            shop_count = Order.objects.filter(user=user).count()
            for order in shop_orders:
                # Get first item name
                first_item = order.items.first()
                item_name = first_item.product.name if first_item else 'Order'
                activities.append({
                    'type': 'shop_order',
                    'icon': 'fa-shopping-cart',
                    'title': f'Order #{order.order_number} - {item_name}',
                    'date': order.created_at,
                    'url': f'/shop/orders/{order.order_number}/',
                    'status': order.status
                })
        except Exception as e:
            logger.debug(f"Could not fetch shop orders: {e}")

        # Fetch Pharmacy orders
        try:
            from pharmacy.models import Order
            pharmacy_orders = Order.objects.filter(user=user).prefetch_related('items__medicine').order_by('-created_at')[:5]
            pharmacy_count = Order.objects.filter(user=user).count()
            for order in pharmacy_orders:
                # Get first medicine name
                first_item = order.items.first()
                medicine_name = first_item.medicine.name if first_item else 'Order'
                activities.append({
                    'type': 'pharmacy_order',
                    'icon': 'fa-pills',
                    'title': f'Order #{order.order_number} - {medicine_name}',
                    'date': order.created_at,
                    'url': f'/pharmacy/orders/{order.order_number}/',
                    'status': order.status
                })
        except Exception as e:
            logger.debug(f"Could not fetch pharmacy orders: {e}")

        # Sort all activities by date and limit to 10 most recent
        activities.sort(key=lambda x: x['date'], reverse=True)
        context['activities'] = activities[:10]

        # Add counts for statistics
        context['rent_count'] = rent_count
        context['ride_count'] = ride_count
        context['food_count'] = food_count
        context['shop_count'] = shop_count
        context['pharmacy_count'] = pharmacy_count

        # Also provide available services for easy access
        context['available_services'] = [
            {'name': 'Rent', 'icon': 'fa-home', 'url': '/rent/'},
            {'name': 'Shop', 'icon': 'fa-shopping-cart', 'url': '/shop/'},
            {'name': 'Food', 'icon': 'fa-utensils', 'url': '/food/'},
            {'name': 'Pharmacy', 'icon': 'fa-pills', 'url': '/pharmacy/'},
            {'name': 'Ride', 'icon': 'fa-car', 'url': '/ride/'},
        ]

    # Add notifications
    from .notification_models import Notification
    recent_notifications = Notification.objects.filter(
        user=user,
        channel='in_app'
    ).order_by('-created_at')[:5]  # Get 5 most recent notifications

    unread_notifications_count = Notification.objects.filter(
        user=user,
        channel='in_app',
        read_at__isnull=True
    ).count()

    context['recent_notifications'] = recent_notifications
    context['unread_notifications_count'] = unread_notifications_count

    return render(request, 'accounts/dashboard.html', context)

@login_required
def profile_setup_view(request):
    """Initial profile setup after signup"""
    user = request.user
    
    # Profile setup no longer needed - users can go directly to profile page
    # Redirect to dashboard
    messages.info(request, 'Welcome! You can update your profile anytime.')
    return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        try:
            # Update user basic information
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.phone_number = request.POST.get('phone_number', '').strip()
            user.location = request.POST.get('location', '').strip()
            user.bio = request.POST.get('bio', '').strip()
            
            # Handle profile picture
            if 'profile_picture' in request.FILES:
                user.profile_picture = request.FILES['profile_picture']
            
            user.save()
            
            if False:  # DISABLED
                # Handle worker profile setup
                from core.models import Skill
                from .models import WorkerProfile
                
                worker_profile, created = WorkerProfile.objects.get_or_create(user=user)
                
                # Update worker profile fields
                worker_profile.experience_years = int(request.POST.get('experience_years', 0) or 0)
                worker_profile.hourly_rate = float(request.POST.get('hourly_rate', 0) or 0) if request.POST.get('hourly_rate') else None
                worker_profile.availability = 'availability' in request.POST
                worker_profile.portfolio = request.POST.get('portfolio', '').strip()
                worker_profile.education = request.POST.get('education', '').strip()
                worker_profile.certifications = request.POST.get('certifications', '').strip()
                
                worker_profile.save()
                
                # Handle skills
                selected_skills = request.POST.getlist('skills')
                if selected_skills:
                    skills = Skill.objects.filter(id__in=selected_skills)
                    worker_profile.skills.set(skills)
                
            elif False:  # DISABLED
                # Handle client profile setup
                from .models import ClientProfile
                
                client_profile, created = ClientProfile.objects.get_or_create(user=user)
                
                client_profile.company_name = request.POST.get('company_name', '').strip()
                client_profile.industry = request.POST.get('industry', '').strip()
                client_profile.business_description = request.POST.get('business_description', '').strip()
                
                client_profile.save()
            
            messages.success(request, 'Profile setup completed! Welcome to Soma Ko.')
            return redirect('accounts:dashboard')
            
        except Exception as e:
            logger.error(f"Error in profile setup for user {user.username}: {str(e)}")
            messages.error(request, 'There was an error setting up your profile. Please try again.')
    
    # GET request - prepare context
    context = {
        'user': user,
        'is_setup': True,
    }
    
    # Add skills for workers
    if False:  # DISABLED
        from core.models import Skill
        context['all_skills'] = Skill.objects.all().order_by('name')
    
    return render(request, 'accounts/profile_setup.html', context)

class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    html_email_template_name = 'emails/password_reset_email.html'
    success_url = reverse_lazy('accounts:password_reset_done')
    
    def form_valid(self, form):
        """Override to use custom email utility"""
        try:
            email = form.cleaned_data['email']
            logger.info(f"Password reset requested for email: {email}")
            
            # Get users with this email
            users = form.get_users(email)
            
            for user in users:
                # Generate reset link
                from django.contrib.auth.tokens import default_token_generator
                from django.utils.http import urlsafe_base64_encode
                from django.utils.encoding import force_bytes

                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_link = self.request.build_absolute_uri(
                    reverse_lazy('accounts:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
                )

                # Send email using custom utility
                send_password_reset_email(user, reset_link)
                logger.info(f"Password reset email sent to {email}")
                messages.success(self.request, 'Password reset email has been sent! Please check your inbox.')
            
            if not users:
                logger.warning(f"Password reset requested for non-existent email: {email}")
                # Don't reveal that the user doesn't exist for security
                messages.success(self.request, 'If an account with that email exists, a password reset email has been sent.')
            
            logger.info(f"Password reset process completed for email: {email}")
            return redirect(self.get_success_url())
            
        except Exception as e:
            logger.error(f"Error in password reset for email {email}: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Show a user-friendly error message
            messages.error(self.request, 'Sorry, there was an error processing your request. Please try again or contact support.')
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        """Add extra context for email templates"""
        context = super().get_context_data(**kwargs)
        context.update({
            'current_time': timezone.now(),
            'request_ip': get_client_ip(self.request),
            'current_year': timezone.now().year,
            'domain': self.request.get_host(),
            'site_name': 'Soma Ko Ghana',
        })
        return context

class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'

    def get_success_url(self):
        """Dynamically determine success URL based on source PWA"""
        return get_pwa_redirect_url(self.request)
    
    def form_valid(self, form):
        """Override to send notification email after password reset"""
        response = super().form_valid(form)
        
        # Get the user whose password was reset
        user = form.user
        
        # Send password reset success notification using new utility function
        try:
            send_password_changed_email(user, self.request)
            logger.info(f"Password reset success notification sent to: {user.email}")
        except Exception as e:
            logger.error(f"Failed to send password reset success email to {user.email}: {str(e)}")
        
        return response

class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'

    def get(self, request, *args, **kwargs):
        """Redirect to appropriate PWA dashboard based on source"""
        redirect_url = get_pwa_redirect_url(request)
        return redirect(redirect_url)


# PWA Password Reset Views
class PWAPasswordResetView(PasswordResetView):
    """PWA-specific password reset view - uses 4-digit OTP code"""
    template_name = 'accounts/pwa_password_reset.html'
    success_url = reverse_lazy('accounts:pwa_password_reset_done')

    def form_valid(self, form):
        """Generate and send 4-digit OTP code instead of reset link"""
        try:
            from .models import VerificationCode
            
            email = form.cleaned_data['email']
            users = form.get_users(email)

            for user in users:
                # Generate 4-digit OTP code
                verification_code = VerificationCode.generate_for_user(
                    user=user,
                    purpose='password_reset',
                    ttl_minutes=15  # Code expires in 15 minutes
                )

                # Send OTP code via email
                from django.core.mail import send_mail
                from django.template.loader import render_to_string
                
                subject = 'Password Reset Code - Soma Ko'
                context = {
                    'user': user,
                    'code': verification_code.code,
                    'expires_minutes': 15,
                }
                
                # Try HTML email first, fallback to plain text
                try:
                    html_message = render_to_string('emails/password_reset_otp_email.html', context)
                    plain_message = f"""
Hi {user.first_name or user.username},

Your password reset code is: {verification_code.code}

This code will expire in 15 minutes.

If you didn't request this, please ignore this email.

Best regards,
Soma Ko Team
                    """.strip()
                    
                    send_mail(
                        subject,
                        plain_message,
                        'noreply@somako.com',
                        [user.email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                except Exception as email_error:
                    # Fallback to plain text only
                    logger.warning(f"HTML email failed, using plain text: {email_error}")
                    plain_message = f"""
Hi {user.first_name or user.username},

Your password reset code is: {verification_code.code}

This code will expire in 15 minutes.

If you didn't request this, please ignore this email.

Best regards,
Soma Ko Team
                    """.strip()
                    
                    send_mail(
                        subject,
                        plain_message,
                        'noreply@somako.com',
                        [user.email],
                        fail_silently=False,
                    )
                
                logger.info(f"PWA password reset OTP sent to {email}")
                
                # Store email in session for verification step
                self.request.session['password_reset_email'] = email
                # Store source PWA for later redirect to login page
                pwa_redirect = get_pwa_redirect_url(self.request, redirect_to='login')
                self.request.session['password_reset_redirect'] = pwa_redirect

            messages.success(self.request, f'A 4-digit verification code has been sent to {email}')
            return redirect(self.get_success_url())

        except Exception as e:
            logger.error(f"Error sending PWA password reset OTP: {str(e)}")
            messages.error(self.request, 'An error occurred. Please try again.')
            return self.form_invalid(form)


class PWAPasswordResetVerifyView(View):
    """Verify OTP code and allow password reset"""
    template_name = 'accounts/pwa_password_reset_verify.html'
    
    def get(self, request):
        """Show OTP verification form"""
        email = request.session.get('password_reset_email')
        if not email:
            messages.error(request, 'Session expired. Please request a new code.')
            return redirect('accounts:pwa_password_reset')
        
        return render(request, self.template_name, {'email': email})
    
    def post(self, request):
        """Verify OTP code"""
        from .models import VerificationCode
        from django.contrib.auth import get_user_model
        
        email = request.session.get('password_reset_email')
        code = request.POST.get('code', '').strip()
        
        if not email:
            messages.error(request, 'Session expired. Please request a new code.')
            return redirect('accounts:pwa_password_reset')
        
        if not code or len(code) != 4:
            messages.error(request, 'Please enter a valid 4-digit code.')
            return render(request, self.template_name, {'email': email})
        
        try:
            User = get_user_model()
            user = User.objects.get(email=email)
            
            # Find valid verification code
            verification_codes = VerificationCode.objects.filter(
                user=user,
                purpose='password_reset',
                used=False
            ).order_by('-created_at')
            
            valid_code = None
            for vc in verification_codes:
                if vc.is_valid(code):
                    valid_code = vc
                    break
            
            if valid_code:
                # Mark code as used
                valid_code.used = True
                valid_code.save()
                
                # Store user ID in session for password reset form
                request.session['password_reset_user_id'] = user.id
                request.session['password_reset_verified'] = True
                
                messages.success(request, 'Code verified! Please enter your new password.')
                return redirect('accounts:pwa_password_reset_new_password')
            else:
                messages.error(request, 'Invalid or expired code. Please try again.')
                return render(request, self.template_name, {'email': email})
                
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('accounts:pwa_password_reset')
        except Exception as e:
            logger.error(f"Error verifying OTP: {str(e)}")
            messages.error(request, 'An error occurred. Please try again.')
            return render(request, self.template_name, {'email': email})


class PWAPasswordResetNewPasswordView(View):
    """Set new password after OTP verification"""
    template_name = 'accounts/pwa_password_reset_new_password.html'
    
    def get(self, request):
        """Show new password form"""
        if not request.session.get('password_reset_verified'):
            messages.error(request, 'Please verify your code first.')
            return redirect('accounts:pwa_password_reset')
        
        return render(request, self.template_name)
    
    def post(self, request):
        """Set new password"""
        from django.contrib.auth import get_user_model
        
        if not request.session.get('password_reset_verified'):
            messages.error(request, 'Please verify your code first.')
            return redirect('accounts:pwa_password_reset')
        
        user_id = request.session.get('password_reset_user_id')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not new_password1 or not new_password2:
            messages.error(request, 'Please fill in both password fields.')
            return render(request, self.template_name)
        
        if new_password1 != new_password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, self.template_name)
        
        if len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, self.template_name)
        
        try:
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            # Set new password
            user.set_password(new_password1)
            user.save()
            
            # Get redirect URL and PWA app before clearing session
            redirect_url = request.session.get('password_reset_redirect', 'accounts:pwa_login')
            source_pwa_app = request.session.get('source_pwa_app', 'food')

            request.session.pop('password_reset_email', None)
            request.session.pop('password_reset_user_id', None)
            request.session.pop('password_reset_verified', None)
            request.session.pop('password_reset_redirect', None)

            # Send notification email
            try:
                send_password_changed_email(user, request)
                logger.info(f"Password changed successfully for {user.email}")
            except Exception as e:
                logger.error(f"Failed to send password changed email: {str(e)}")

            messages.success(request, 'Your password has been reset successfully! Please login with your new password.')
            # Redirect to the appropriate PWA login page with app parameter
            from django.urls import reverse
            login_url = reverse(redirect_url)
            return redirect(f'{login_url}?app={source_pwa_app}')
            
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('accounts:pwa_password_reset')
        except Exception as e:
            logger.error(f"Error setting new password: {str(e)}")
            messages.error(request, 'An error occurred. Please try again.')
            return render(request, self.template_name)


class PWAPasswordResetDoneView(PasswordResetDoneView):
    """PWA password reset done view"""
    template_name = 'accounts/pwa_password_reset_done.html'


class PWAPasswordResetConfirmView(PasswordResetConfirmView):
    """PWA password reset confirm view"""
    template_name = 'accounts/pwa_password_reset_confirm.html'

    def get_success_url(self):
        """Dynamically determine success URL based on source PWA"""
        return get_pwa_redirect_url(self.request)

    def form_valid(self, form):
        """Override to send notification after password reset"""
        response = super().form_valid(form)

        user = form.user
        logger.info(f"PWA password reset completed for user: {user.username}")

        # Send password changed confirmation email
        try:
            send_password_changed_email(user, self.request)
        except Exception as e:
            logger.error(f"Error sending password change confirmation: {str(e)}")

        return response


class PWAPasswordResetCompleteView(PasswordResetCompleteView):
    """PWA password reset complete view (now redirects to Food PWA)"""
    template_name = 'accounts/pwa_password_reset_complete.html'


# Main Website OTP Password Reset Views
class OTPPasswordResetView(PasswordResetView):
    """Main website OTP-based password reset view - uses 4-digit OTP code"""
    template_name = 'accounts/otp_password_reset.html'
    success_url = reverse_lazy('accounts:otp_password_reset_done')

    def form_valid(self, form):
        """Generate and send 4-digit OTP code instead of reset link"""
        try:
            from .models import VerificationCode
            
            email = form.cleaned_data['email']
            users = form.get_users(email)

            for user in users:
                # Generate 4-digit OTP code
                verification_code = VerificationCode.generate_for_user(
                    user=user,
                    purpose='password_reset',
                    ttl_minutes=15  # Code expires in 15 minutes
                )

                # Send OTP code via email
                from django.core.mail import send_mail
                from django.template.loader import render_to_string
                
                subject = 'Password Reset Code - Soma Ko'
                context = {
                    'user': user,
                    'code': verification_code.code,
                    'expires_minutes': 15,
                }
                
                # Try HTML email first, fallback to plain text
                try:
                    html_message = render_to_string('emails/password_reset_otp_email.html', context)
                    plain_message = f"""
Hi {user.first_name or user.username},

Your password reset code is: {verification_code.code}

This code will expire in 15 minutes.

If you didn't request this, please ignore this email.

Best regards,
Soma Ko Team
                    """.strip()
                    
                    send_mail(
                        subject,
                        plain_message,
                        'noreply@somako.com',
                        [user.email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                except Exception as email_error:
                    # Fallback to plain text only
                    logger.warning(f"HTML email failed, using plain text: {email_error}")
                    plain_message = f"""
Hi {user.first_name or user.username},

Your password reset code is: {verification_code.code}

This code will expire in 15 minutes.

If you didn't request this, please ignore this email.

Best regards,
Soma Ko Team
                    """.strip()
                    
                    send_mail(
                        subject,
                        plain_message,
                        'noreply@somako.com',
                        [user.email],
                        fail_silently=False,
                    )
                
                logger.info(f"Main website password reset OTP sent to {email}")
                
                # Store email in session for verification step
                self.request.session['password_reset_email'] = email
                # Store that this is main website reset (not PWA)
                self.request.session['password_reset_source'] = 'main_website'

            messages.success(self.request, f'A 4-digit verification code has been sent to {email}')
            return redirect(self.get_success_url())

        except Exception as e:
            logger.error(f"Error sending main website password reset OTP: {str(e)}")
            messages.error(self.request, 'An error occurred. Please try again.')
            return self.form_invalid(form)


class OTPPasswordResetVerifyView(View):
    """Verify OTP code for main website password reset"""
    template_name = 'accounts/otp_password_reset_verify.html'
    
    def get(self, request):
        """Show OTP verification form"""
        email = request.session.get('password_reset_email')
        source = request.session.get('password_reset_source')
        
        if not email or source != 'main_website':
            messages.error(request, 'Session expired. Please request a new code.')
            return redirect('accounts:otp_password_reset')
        
        return render(request, self.template_name, {'email': email})
    
    def post(self, request):
        """Verify OTP code"""
        from .models import VerificationCode
        from django.contrib.auth import get_user_model
        
        email = request.session.get('password_reset_email')
        source = request.session.get('password_reset_source')
        code = request.POST.get('code', '').strip()
        
        if not email or source != 'main_website':
            messages.error(request, 'Session expired. Please request a new code.')
            return redirect('accounts:otp_password_reset')
        
        if not code or len(code) != 4:
            messages.error(request, 'Please enter a valid 4-digit code.')
            return render(request, self.template_name, {'email': email})
        
        try:
            User = get_user_model()
            user = User.objects.get(email=email)
            
            # Find valid verification code
            verification_codes = VerificationCode.objects.filter(
                user=user,
                purpose='password_reset',
                used=False
            ).order_by('-created_at')
            
            valid_code = None
            for vc in verification_codes:
                if vc.is_valid(code):
                    valid_code = vc
                    break
            
            if valid_code:
                # Mark code as used
                valid_code.used = True
                valid_code.save()
                
                # Store user ID in session for password reset form
                request.session['password_reset_user_id'] = user.id
                request.session['password_reset_verified'] = True
                
                messages.success(request, 'Code verified! Please enter your new password.')
                return redirect('accounts:otp_password_reset_new_password')
            else:
                messages.error(request, 'Invalid or expired code. Please try again.')
                return render(request, self.template_name, {'email': email})
                
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('accounts:otp_password_reset')
        except Exception as e:
            logger.error(f"Error verifying main website OTP: {str(e)}")
            messages.error(request, 'An error occurred. Please try again.')
            return render(request, self.template_name, {'email': email})


class OTPPasswordResetNewPasswordView(View):
    """Set new password for main website after OTP verification"""
    template_name = 'accounts/otp_password_reset_new_password.html'
    
    def get(self, request):
        """Show new password form"""
        source = request.session.get('password_reset_source')
        if not request.session.get('password_reset_verified') or source != 'main_website':
            messages.error(request, 'Please verify your code first.')
            return redirect('accounts:otp_password_reset')
        
        return render(request, self.template_name)
    
    def post(self, request):
        """Set new password"""
        from django.contrib.auth import get_user_model
        
        source = request.session.get('password_reset_source')
        if not request.session.get('password_reset_verified') or source != 'main_website':
            messages.error(request, 'Please verify your code first.')
            return redirect('accounts:otp_password_reset')
        
        user_id = request.session.get('password_reset_user_id')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not new_password1 or not new_password2:
            messages.error(request, 'Please fill in both password fields.')
            return render(request, self.template_name)
        
        if new_password1 != new_password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, self.template_name)
        
        if len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, self.template_name)
        
        try:
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            # Set new password
            user.set_password(new_password1)
            user.save()
            
            # Clear session
            request.session.pop('password_reset_email', None)
            request.session.pop('password_reset_user_id', None)
            request.session.pop('password_reset_verified', None)
            request.session.pop('password_reset_source', None)

            # Send notification email
            try:
                send_password_changed_email(user, request)
                logger.info(f"Main website password changed successfully for {user.email}")
            except Exception as e:
                logger.error(f"Failed to send password changed email: {str(e)}")

            messages.success(request, 'Your password has been reset successfully! Please login with your new password.')
            return redirect('accounts:login')
            
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('accounts:otp_password_reset')
        except Exception as e:
            logger.error(f"Error setting new password: {str(e)}")
            messages.error(request, 'An error occurred. Please try again.')
            return render(request, self.template_name)


class OTPPasswordResetDoneView(PasswordResetDoneView):
    """Main website OTP password reset done view"""
    template_name = 'accounts/otp_password_reset_done.html'

    def get(self, request, *args, **kwargs):
        return redirect('food_pwa:dashboard')


def public_profile_view(request, username):
    """Public profile view for users based on their account type"""
    try:
        user = User.objects.get(username=username, is_active=True)
        
        # Check if profile is visible to public
        if not user.profile_visibility:
            return render(request, 'accounts/profile_private.html', {'profile_user': user})
        
        context = {
            'profile_user': user,
            'is_own_profile': request.user.is_authenticated and request.user == user,
        }
        
        if False:  # DISABLED
            # Get worker-specific data
            try:
                worker_profile = user.worker_profile
                context['worker_profile'] = worker_profile
                
                # Get portfolio items
                from core.models import PortfolioItem
                context['portfolio_items'] = PortfolioItem.objects.filter(
                    worker_profile=worker_profile
                ).order_by('-created_at')[:6]  # Show latest 6 items
                
                # Get worker certifications and education
                context['certifications'] = worker_profile.worker_certifications.all()
                context['education'] = worker_profile.worker_education.all()
                
                # Calculate completion percentage for display
                context['profile_completion'] = worker_profile.profile_completion
                
            except:
                # Worker profile doesn't exist
                context['worker_profile'] = None
            
            return render(request, 'accounts/public_profile_worker.html', context)
            
        elif False:  # DISABLED
            # Get client-specific data
            try:
                client_profile = user.client_profile
                context['client_profile'] = client_profile
                
                # Get client's posted jobs (public ones only)
                from core.models import Job
                context['recent_jobs'] = Job.objects.filter(
                    client=user,
                    status__in=['open', 'in_progress']
                ).order_by('-created_at')[:5]  # Show latest 5 jobs
                
            except:
                # Client profile doesn't exist
                context['client_profile'] = None
            
            return render(request, 'accounts/public_profile_client.html', context)
            
    except User.DoesNotExist:
        return render(request, 'accounts/profile_not_found.html', status=404)


def browse_profiles_view(request):
    """Browse client profiles - only accessible to workers"""
    # Restrict access to workers only
    if not request.user.is_authenticated:
        from django.contrib import messages
        messages.error(request, 'Please log in to browse client profiles.')
        return redirect('accounts:login')

    # All users can browse profiles now

    search_query = request.GET.get('q', '')

    # Base queryset for public profiles
    users = User.objects.filter(
        is_active=True,
        profile_visibility=True
    ).order_by('-date_joined', 'first_name', 'last_name')

    # Apply search filter
    if search_query:
        users = users.filter(
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(username__icontains=search_query) |
            models.Q(bio__icontains=search_query)
        )

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users, 12)  # 12 profiles per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'users': page_obj,
        'search_query': search_query,
        'total_count': users.count(),
    }

    return render(request, 'accounts/browse_profiles.html', context)


# ============================================
# Role Application Views
# ============================================

@login_required
def apply_for_role(request):
    """View for users to apply for a new service role"""
    if request.method == 'POST':
        form = RoleApplicationForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            application.save()

            messages.success(
                request,
                f'Your application for {application.get_role_display()} has been submitted! '
                'You will be notified once it has been reviewed.'
            )
            return redirect('accounts:my_role_applications')
    else:
        form = RoleApplicationForm(user=request.user)

    # Get user's current roles
    current_roles = request.user.get_roles_display()

    context = {
        'form': form,
        'current_roles': current_roles,
    }

    return render(request, 'accounts/apply_for_role.html', context)


@login_required
def my_role_applications(request):
    """View user's role applications and their status"""
    applications = RoleApplication.objects.filter(
        user=request.user
    ).select_related('reviewed_by').order_by('-created_at')

    # Get pending applications
    pending = applications.filter(status='pending')
    approved = applications.filter(status='approved')
    rejected = applications.filter(status='rejected')

    context = {
        'applications': applications,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
    }

    return render(request, 'accounts/my_role_applications.html', context)


@login_required
def role_dashboard_redirect(request):
    """Redirect user to appropriate dashboard based on their roles"""
    user = request.user
    roles = user.get_roles_list()

    # Define dashboard URLs for each role
    role_dashboards = {
        'landlord': 'rent:dashboard',
        'tenant': 'rent:dashboard',
        'equipment_owner': 'rent:dashboard',
        'equipment_renter': 'rent:dashboard',
        'seller': 'shop:dashboard',
        'buyer': 'shop:dashboard',
        'pharmacy_owner': 'pharmacy:dashboard',
        'patient': 'pharmacy:dashboard',
        'restaurant_owner': 'food:dashboard',
        'customer': 'food:dashboard',
        'driver': 'ride:dashboard',
        'rider': 'ride:dashboard',
    }

    # Get first role that has a dashboard
    for role in roles:
        if role in role_dashboards:
            try:
                return redirect(role_dashboards[role])
            except:
                pass

    # Default to general dashboard
    messages.info(request, 'Welcome! Apply for roles to access app-specific dashboards.')
    return redirect('core:home')

# ============================================
# PWA-Specific Authentication Views
# ============================================

from django.contrib.auth import logout as auth_logout

def pwa_login_view(request):
    """
    PWA-specific login view that redirects to appropriate PWA app
    """
    if request.user.is_authenticated:
        # Check if user is a delivery driver and redirect to rider dashboard
        if request.user.has_role('delivery_driver') or request.user.has_role('rider'):
            from django.urls import reverse
            return redirect(reverse('express_pwa:rider_dashboard'))
        
        # Check if user has a driver profile for ride app and redirect to driver dashboard
        try:
            from ride.models import DriverProfile
            driver_profile = DriverProfile.objects.filter(user=request.user).first()
            if driver_profile:
                return redirect('ride:driver_dashboard')
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking driver profile for user {request.user.username}: {str(e)}")
        
        # Get the 'next' parameter or default to Food PWA
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        # Default to Food PWA instead of core
        return redirect('/pwa/food/')
    
    # Determine which PWA app from referer or next parameter
    app_context = {}
    next_url = request.GET.get('next', '')
    
    # Set app-specific colors and context based on URL
    if '/pwa/shop/' in next_url or 'shop' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Shop',
            'app_icon': 'fas fa-shopping-bag',
            'app_color': '#3b82f6',
            'app_color_dark': '#2563eb',
            'pwa_home_url': '/pwa/shop/',
        }
    elif '/pwa/food/' in next_url or 'food' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Food',
            'app_icon': 'fas fa-utensils',
            'app_color': '#ea580c',
            'app_color_dark': '#c2410c',
            'pwa_home_url': '/pwa/food/',
        }
    elif '/pwa/ride/' in next_url or 'ride' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Ride',
            'app_icon': 'fas fa-car',
            'app_color': '#8b5cf6',
            'app_color_dark': '#7c3aed',
            'pwa_home_url': '/pwa/ride/',
        }
    elif '/pwa/rent/' in next_url or 'rent' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Rent',
            'app_icon': 'fas fa-home',
            'app_color': '#059669',
            'app_color_dark': '#047857',
            'pwa_home_url': '/pwa/rent/',
        }
    elif '/pwa/pharmacy/' in next_url or 'pharmacy' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Pharmacy',
            'app_icon': 'fas fa-pills',
            'app_color': '#dc2626',
            'app_color_dark': '#b91c1c',
            'pwa_home_url': '/pwa/pharmacy/',
        }
    elif '/pwa/express/' in next_url or 'express' in request.GET.get('app', ''):
        app_context = {
            'app_name': 'Soma Ko Express',
            'app_icon': 'fas fa-shipping-fast',
            'app_color': '#06b6d4',
            'app_color_dark': '#0891b2',
            'pwa_home_url': '/pwa/express/',
        }
    else:
        # Default context - use Food PWA as default
        app_context = {
            'app_name': 'Soma Ko Food',
            'app_icon': 'fas fa-utensils',
            'app_color': '#ea580c',
            'app_color_dark': '#c2410c',
            'pwa_home_url': '/pwa/food/',
        }
    
    if request.method == 'POST':
        from django.contrib.auth import authenticate, login
        username = request.POST.get('username')
        password = request.POST.get('password')
        next_url = request.POST.get('next', app_context['pwa_home_url'])
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Debug: Log user roles
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"User {user.username} attempting login with roles: {user.service_roles}")
            logger.info(f"User roles list: {user.get_roles_list()}")
            
            # Get the target app from next_url or app parameter
            target_app = request.GET.get('app', '')
            if not target_app:
                if '/pwa/food/' in next_url:
                    target_app = 'food'
                elif '/pwa/pharmacy/' in next_url:
                    target_app = 'pharmacy'
                elif '/pwa/shop/' in next_url:
                    target_app = 'shop'
                elif '/pwa/rent/' in next_url:
                    target_app = 'rent'
                elif '/pwa/ride/' in next_url:
                    target_app = 'ride'
                elif '/pwa/express/' in next_url:
                    target_app = 'express'
            
            # Check user type restrictions for specific apps
            user_roles = user.get_roles_list()
            is_general_user = user.has_role('general') or 'general' in user.service_roles
            
            # Food app restriction: only general users or restaurant owners
            if target_app == 'food':
                is_restaurant_owner = user.has_role('restaurant_owner') or 'restaurant_owner' in user.service_roles
                if not (is_general_user or is_restaurant_owner):
                    logger.warning(f"User {user.username} denied access to food app. Roles: {user.service_roles}")
                    app_context['error'] = 'Access denied. Only general users or restaurant owners can access the Food app.'
                    app_context['next'] = next_url or app_context['pwa_home_url']
                    return render(request, 'pwa/login.html', app_context)
            
            # Pharmacy app restriction: only general users or pharmacy owners
            if target_app == 'pharmacy':
                is_pharmacy_owner = user.has_role('pharmacy_owner') or 'pharmacy_owner' in user.service_roles
                if not (is_general_user or is_pharmacy_owner):
                    logger.warning(f"User {user.username} denied access to pharmacy app. Roles: {user.service_roles}")
                    app_context['error'] = 'Access denied. Only general users or pharmacy owners can access the Pharmacy app.'
                    app_context['next'] = next_url or app_context['pwa_home_url']
                    return render(request, 'pwa/login.html', app_context)
            
            # Ride app restriction: only general users or drivers
            if target_app == 'ride':
                is_driver = user.has_role('driver') or 'driver' in user.service_roles
                if not (is_general_user or is_driver):
                    logger.warning(f"User {user.username} denied access to ride app. Roles: {user.service_roles}")
                    app_context['error'] = 'Access denied. Only general users or drivers can access the Ride app.'
                    app_context['next'] = next_url or app_context['pwa_home_url']
                    return render(request, 'pwa/login.html', app_context)
            
            # Shop app restriction: only general users or sellers
            if target_app == 'shop':
                is_seller = user.has_role('seller') or 'seller' in user.service_roles
                if not (is_general_user or is_seller):
                    logger.warning(f"User {user.username} denied access to shop app. Roles: {user.service_roles}")
                    app_context['error'] = 'Access denied. Only general users or sellers can access the Shop app.'
                    app_context['next'] = next_url or app_context['pwa_home_url']
                    return render(request, 'pwa/login.html', app_context)
            
            # Rent app restriction: only general users, landlords, or equipment owners
            if target_app == 'rent':
                is_landlord = user.has_role('landlord') or 'landlord' in user.service_roles
                is_equipment_owner = user.has_role('equipment_owner') or 'equipment_owner' in user.service_roles
                if not (is_general_user or is_landlord or is_equipment_owner):
                    logger.warning(f"User {user.username} denied access to rent app. Roles: {user.service_roles}")
                    app_context['error'] = 'Access denied. Only general users, landlords, or equipment owners can access the Rent app.'
                    app_context['next'] = next_url or app_context['pwa_home_url']
                    return render(request, 'pwa/login.html', app_context)
            
            # User passed all checks, proceed with login
            login(request, user)
            logger.info(f"User {user.username} logged in successfully with roles: {user.service_roles}")
            logger.info(f"Has rider role: {user.has_role('rider')}")
            
            # Check if user is a delivery driver and redirect to rider dashboard
            # Alternative check methods for debugging
            is_delivery_driver = user.has_role('delivery_driver')
            is_rider_method1 = user.has_role('rider')
            is_rider_method2 = 'rider' in user.service_roles
            is_delivery_driver_method2 = 'delivery_driver' in user.service_roles
            
            logger.info(f"Delivery driver check: {is_delivery_driver}")
            logger.info(f"Rider check method 1 (has_role): {is_rider_method1}")
            logger.info(f"Rider check method 2 (in service_roles): {is_rider_method2}")
            logger.info(f"Delivery driver check (in service_roles): {is_delivery_driver_method2}")
            
            if is_delivery_driver or is_rider_method1 or is_rider_method2 or is_delivery_driver_method2:
                from django.urls import reverse
                logger.info(f"Redirecting rider {user.username} to rider dashboard")
                try:
                    rider_url = reverse('express_pwa:rider_dashboard')
                    logger.info(f"Rider dashboard URL: {rider_url}")
                    return redirect(rider_url)
                except Exception as e:
                    logger.error(f"Error redirecting to rider dashboard: {e}")
                    # Fall back to express main page
                    return redirect('/pwa/express/')
            
            # Check if user has a driver profile for ride app and redirect to driver dashboard
            try:
                from ride.models import DriverProfile
                driver_profile = DriverProfile.objects.filter(user=user).first()
                if driver_profile:
                    logger.info(f"Redirecting driver {user.username} to driver dashboard")
                    return redirect('ride:driver_dashboard')
            except Exception as e:
                logger.error(f"Error checking driver profile for user {user.username}: {str(e)}")
            
            return redirect(next_url)
        else:
            app_context['error'] = 'Invalid username or password'
    
    app_context['next'] = next_url or app_context['pwa_home_url']
    return render(request, 'pwa/login.html', app_context)


def pwa_logout_view(request):
    """
    PWA-specific logout view that redirects to PWA login
    """
    # Get the next URL or determine from referer
    next_url = request.GET.get('next', '')
    
    # Determine which PWA app
    referer = request.META.get('HTTP_REFERER', '')
    
    if not next_url:
        if '/pwa/shop/' in referer:
            next_url = '/accounts/login/pwa/?app=shop&next=/pwa/shop/'
        elif '/pwa/food/' in referer:
            next_url = '/accounts/login/pwa/?app=food&next=/pwa/food/'
        elif '/pwa/ride/' in referer:
            next_url = '/accounts/login/pwa/?app=ride&next=/pwa/ride/'
        elif '/pwa/rent/' in referer:
            next_url = '/accounts/login/pwa/?app=rent&next=/pwa/rent/'
        elif '/pwa/pharmacy/' in referer:
            next_url = '/accounts/login/pwa/?app=pharmacy&next=/pwa/pharmacy/'
        else:
            next_url = '/accounts/login/pwa/'
    
    # Log the user out
    auth_logout(request)
    messages.success(request, 'You have been successfully logged out.')
    
    return redirect(next_url)


def pwa_profile_view(request):
    """
    Universal PWA profile index view
    """
    if not request.user.is_authenticated:
        return redirect('accounts:pwa_login')
    
    # Get the app context from referer or session
    app_context = get_pwa_app_context(request)
    
    # Add user stats
    app_context['stats'] = {
        'orders': 0,  # Will be dynamically calculated
        'saved': 0,
        'reviews': 0,
    }
    
    return render(request, 'pwa/profile/index.html', app_context)


@login_required
def pwa_profile_edit_view(request):
    """PWA profile edit view"""
    app_context = get_pwa_app_context(request)
    
    if request.method == 'POST':
        try:
            user = request.user
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.email = request.POST.get('email', '').strip()
            user.phone_number = request.POST.get('phone_number', '').strip()
            user.location = request.POST.get('location', '').strip()
            user.bio = request.POST.get('bio', '').strip()
            
            if 'profile_picture' in request.FILES:
                profile_pic = request.FILES['profile_picture']
                if profile_pic.size <= 5 * 1024 * 1024:  # 5MB limit
                    if user.profile_picture:
                        try:
                            user.profile_picture.delete(save=False)
                        except:
                            pass
                    user.profile_picture = profile_pic
            
            user.save()
            messages.success(request, 'Profile updated successfully!')
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
        
        return redirect('accounts:pwa_profile_edit')
    
    return render(request, 'pwa/profile/edit.html', app_context)


@login_required
def pwa_profile_password_view(request):
    """PWA password change view"""
    app_context = get_pwa_app_context(request)
    
    if request.method == 'POST':
        from django.contrib.auth import update_session_auth_hash
        
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not request.user.check_password(old_password):
            messages.error(request, 'Your current password is incorrect.')
        elif new_password1 != new_password2:
            messages.error(request, 'The two password fields did not match.')
        elif len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            try:
                request.user.set_password(new_password1)
                request.user.save()
                update_session_auth_hash(request, request.user)
                
                # Send password change notification
                try:
                    send_password_changed_email(request.user, request)
                except Exception as e:
                    logger.error(f"Error sending password change email: {str(e)}")
                
                messages.success(request, 'Your password has been updated successfully!')
            except Exception as e:
                messages.error(request, f'Error changing password: {str(e)}')
        
        return redirect('accounts:pwa_profile_password')
    
    return render(request, 'pwa/profile/password.html', app_context)


@login_required
def pwa_profile_settings_view(request):
    """PWA settings view"""
    app_context = get_pwa_app_context(request)
    
    # Get or create user settings (you might want to create a UserSettings model)
    app_context['settings'] = {
        'theme': 'light',
        'compact_view': False,
        'push_notifications': True,
        'email_notifications': True,
        'sms_notifications': False,
        'location_services': True,
        'activity_status': True,
        'language': 'en',
        'currency': 'NGN',
        'autoplay_videos': True,
        'data_saver': False,
    }
    
    if request.method == 'POST':
        # Save settings logic here
        messages.success(request, 'Settings updated successfully!')
        return redirect('accounts:pwa_profile_settings')
    
    return render(request, 'pwa/profile/settings.html', app_context)


@login_required
def pwa_profile_orders_view(request):
    """PWA orders history view"""
    app_context = get_pwa_app_context(request)
    
    # Get orders based on the service
    app_context['orders'] = []  # Will be populated from actual order models
    
    return render(request, 'pwa/profile/orders.html', app_context)


@login_required
def pwa_profile_saved_view(request):
    """PWA saved items view"""
    app_context = get_pwa_app_context(request)
    
    # Get saved items based on the service
    app_context['saved_items'] = []  # Will be populated from actual favorite models
    
    return render(request, 'pwa/profile/saved.html', app_context)


def get_pwa_app_context(request):
    """Helper function to get PWA app context from referer or session"""
    referer = request.META.get('HTTP_REFERER', '')
    app = request.GET.get('app', '')
    
    # Determine app from referer or app parameter
    if '/pwa/shop/' in referer or app == 'shop':
        return {
            'service_name': 'Shop',
            'app_color': '#8b5cf6',
            'app_color_dark': '#7c3aed',
            'pwa_home_url': '/pwa/shop/',
        }
    elif '/pwa/food/' in referer or app == 'food':
        return {
            'service_name': 'Food',
            'app_color': '#ea580c',
            'app_color_dark': '#c2410c',
            'pwa_home_url': '/pwa/food/',
        }
    elif '/pwa/ride/' in referer or app == 'ride':
        return {
            'service_name': 'Ride',
            'app_color': '#f59e0b',
            'app_color_dark': '#d97706',
            'pwa_home_url': '/pwa/ride/',
        }
    elif '/pwa/rent/' in referer or app == 'rent':
        return {
            'service_name': 'Rent',
            'app_color': '#0891b2',
            'app_color_dark': '#0e7490',
            'pwa_home_url': '/pwa/rent/',
        }
    elif '/pwa/pharmacy/' in referer or app == 'pharmacy':
        return {
            'service_name': 'Pharmacy',
            'app_color': '#10b981',
            'app_color_dark': '#059669',
            'pwa_home_url': '/pwa/pharmacy/',
        }
    
    # Default to Food PWA
    return {
        'service_name': 'Food',
        'app_color': '#ea580c',
        'app_color_dark': '#c2410c',
        'pwa_home_url': '/pwa/food/',
    }


def pwa_signup_view(request):
    """
    PWA-specific signup view that redirects to appropriate PWA app
    """
    if request.user.is_authenticated:
        # Get the 'next' parameter or default to Food PWA
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        # Default to Food PWA instead of core
        return redirect('/pwa/food/')

    # Determine which PWA app from next parameter
    app_context = {}
    next_url = request.GET.get('next', '')

    # Set app-specific colors and context based on URL
    if '/pwa/shop/' in next_url or 'shop' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Shop',
            'service_icon': 'fa-shopping-bag',
            'primary_color': '#3b82f6',
            'secondary_color': '#2563eb',
            'theme_color': '#3b82f6',
            'pwa_home_url': '/pwa/shop/',
        }
    elif '/pwa/food/' in next_url or 'food' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Food',
            'service_icon': 'fa-utensils',
            'primary_color': '#ea580c',
            'secondary_color': '#c2410c',
            'theme_color': '#ea580c',
            'pwa_home_url': '/pwa/food/',
        }
    elif '/pwa/ride/' in next_url or 'ride' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Ride',
            'service_icon': 'fa-car',
            'primary_color': '#8b5cf6',
            'secondary_color': '#7c3aed',
            'theme_color': '#8b5cf6',
            'pwa_home_url': '/pwa/ride/',
        }
    elif '/pwa/rent/' in next_url or 'rent' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Rent',
            'service_icon': 'fa-home',
            'primary_color': '#059669',
            'secondary_color': '#047857',
            'theme_color': '#059669',
            'pwa_home_url': '/pwa/rent/',
        }
    elif '/pwa/pharmacy/' in next_url or 'pharmacy' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Pharmacy',
            'service_icon': 'fa-pills',
            'primary_color': '#dc2626',
            'secondary_color': '#b91c1c',
            'theme_color': '#dc2626',
            'pwa_home_url': '/pwa/pharmacy/',
        }
    elif '/pwa/express/' in next_url or 'express' in request.GET.get('app', ''):
        app_context = {
            'service_name': 'Express',
            'service_icon': 'fa-shipping-fast',
            'primary_color': '#06b6d4',
            'secondary_color': '#0891b2',
            'theme_color': '#06b6d4',
            'pwa_home_url': '/pwa/express/',
        }
    else:
        # Default context - use Food PWA as default
        app_context = {
            'service_name': 'Food',
            'service_icon': 'fa-utensils',
            'primary_color': '#ea580c',
            'secondary_color': '#c2410c',
            'theme_color': '#ea580c',
            'pwa_home_url': '/pwa/food/',
        }

    if request.method == 'POST':
        from django.contrib.auth import authenticate, login
        from .forms import CustomUserCreationForm

        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Populate additional fields from PWA form (first_name, last_name, phone_number)
            try:
                user.first_name = request.POST.get('first_name', '').strip()
                user.last_name = request.POST.get('last_name', '').strip()
                user.phone_number = request.POST.get('phone_number', '').strip()
                user.save(update_fields=['first_name', 'last_name', 'phone_number'])
            except Exception as e:
                logger.warning(f"Could not save additional signup fields: {e}")
            
            # Send welcome email
            try:
                send_welcome_email(user)
                logger.info(f"Welcome email sent to {user.email}")
            except Exception as e:
                logger.error(f"Error sending welcome email to {user.email}: {str(e)}")
            
            # Auto-login after signup
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # Generate and send verification code, then redirect to verification page
                try:
                    vc = VerificationCode.generate_for_user(user, purpose='signup', ttl_minutes=15)
                    result = send_user_verification_code(user, vc.code)
                    if not result.get('success'):
                        logger.error(f"Failed to send verification code to {user.username}: {result.get('message')}")
                        messages.warning(request, 
                            'Account created successfully! However, we could not send the verification code. '
                            'Please check your phone number and email, then try to resend the code.')
                    else:
                        messages.success(request, 'Account created! A verification code has been sent to your phone/email.')
                except Exception as e:
                    logger.error(f"Failed to generate/send verification code: {e}")
                    messages.warning(request, 
                        'Account created successfully! However, there was an issue sending the verification code. '
                        'Please try to resend the code from the verification page.')
                next_url = request.POST.get('next', app_context['pwa_home_url'])
                verify_url = f"{reverse_lazy('accounts:pwa_verify')}?next={next_url}"
                return redirect(verify_url)
        else:
            app_context['form'] = form
            app_context['errors'] = form.errors

    app_context['next'] = next_url or app_context['pwa_home_url']
    return render(request, 'accounts/pwa_signup.html', app_context)


def pwa_verify_view(request):
    """PWA verification view to enter the 4-digit code after signup."""
    if not request.user.is_authenticated:
        # Preserve next for after verification
        next_url = request.GET.get('next', '/pwa/food/')
        return redirect(f"{reverse_lazy('accounts:pwa_login')}?next={next_url}")

    next_url = request.GET.get('next', '/pwa/food/')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()
        try:
            vc = (
                VerificationCode.objects
                .filter(user=request.user, purpose='signup', used=False)
                .order_by('-created_at')
                .first()
            )
            if not vc:
                messages.error(request, 'No verification code found. Please request a new code.')
            elif vc.is_valid(code):
                request.user.is_verified = True
                request.user.save(update_fields=['is_verified'])
                vc.used = True
                vc.save(update_fields=['used'])
                # Clear resend attempts on success
                if 'verification_resend_attempts' in request.session:
                    del request.session['verification_resend_attempts']
                messages.success(request, 'Your account has been verified!')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid or expired code. Please try again or resend a new code.')
        except Exception as e:
            logger.error(f"OTP verification error for {request.user.username}: {e}")
            messages.error(request, 'Could not verify code. Please try again.')

    # Mask phone/email for display
    phone = getattr(request.user, 'phone_number', '') or getattr(getattr(request.user, 'profile', None), 'phone_number', '') or ''
    email = getattr(request.user, 'email', '')

    def mask(s, keep=2):
        if not s:
            return ''
        if '@' in s:
            name, domain = s.split('@', 1)
            return (name[:keep] + '***@' + domain) if len(name) > keep else ('***@' + domain)
        return s[:keep] + '***' + s[-keep:] if len(s) > keep * 2 else '***'
    
    # Calculate remaining resend attempts
    from django.utils import timezone
    from datetime import timedelta
    session_key = 'verification_resend_attempts'
    attempts = request.session.get(session_key, [])
    cutoff = timezone.now() - timedelta(minutes=10)
    attempts = [ts for ts in attempts if timezone.datetime.fromisoformat(ts) > cutoff]
    remaining_attempts = max(0, 3 - len(attempts))

    context = {
        'next': next_url,
        'masked_phone': mask(phone, 3) if phone else '',
        'masked_email': mask(email, 2) if email else '',
        'remaining_attempts': remaining_attempts,
    }
    return render(request, 'accounts/pwa_verify.html', context)


def pwa_resend_verification_code(request):
    """Resend a new verification code to the logged-in user with rate limiting."""
    if not request.user.is_authenticated:
        return redirect('accounts:pwa_login')

    from django.utils import timezone
    from datetime import timedelta
    
    # Rate limiting: max 3 resends per 10 minutes
    session_key = 'verification_resend_attempts'
    attempts = request.session.get(session_key, [])
    
    # Clean old attempts (older than 10 minutes)
    cutoff = timezone.now() - timedelta(minutes=10)
    attempts = [ts for ts in attempts if timezone.datetime.fromisoformat(ts) > cutoff]
    
    if len(attempts) >= 3:
        wait_time = (timezone.datetime.fromisoformat(attempts[0]) + timedelta(minutes=10) - timezone.now()).seconds // 60 + 1
        messages.error(request, f'Too many resend attempts. Please wait {wait_time} minute(s) before trying again.')
        next_url = request.GET.get('next', '/pwa/food/')
        return redirect(f"{reverse_lazy('accounts:pwa_verify')}?next={next_url}")
    
    try:
        vc = VerificationCode.generate_for_user(request.user, purpose='signup', ttl_minutes=15)
        result = send_user_verification_code(request.user, vc.code)
        
        if result.get('success'):
            # Track this resend
            attempts.append(timezone.now().isoformat())
            request.session[session_key] = attempts
            messages.success(request, 'A new verification code has been sent.')
        else:
            messages.error(request, f"Could not send code: {result.get('message', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to resend verification code: {e}")
        messages.error(request, 'Could not resend code. Please try again later.')

    next_url = request.GET.get('next', '/pwa/food/')
    return redirect(f"{reverse_lazy('accounts:pwa_verify')}?next={next_url}")
