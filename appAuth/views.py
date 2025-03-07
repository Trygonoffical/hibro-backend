import requests

import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.core.mail import send_mail
from home.models import PhoneOTP, User , HomeSlider , Category , Product , ProductImage  , Testimonial , Advertisement , CompanyInfo , About , Menu , CustomPage , Clients , BulkOrderRequest, BulkOrderPrice , Address , Order , OrderItem
from django.shortcuts import get_object_or_404
import random
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny , IsAdminUser
from django.utils import timezone
from datetime import timedelta
from .serializers import UserSerializer 
from home.serializers import CategorySerializer , ProductSerializer , TestimonialSerializer , AdvertisementSerializer ,  CompanyInfoSerializer , AboutSerializer  , MenuSerializer , CustomPageSerializer , ClientsSerializer , BulkOrderRequestSerializer , AddressSerializer , CustomerProfileSerializer , OrderSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.db.models import F, Q , Count
from django.db.models import Sum, Avg, Count, Min, Max
from django.db.models.functions import TruncMonth, TruncDay, TruncYear, Extract
from rest_framework import viewsets , permissions
from rest_framework.parsers import MultiPartParser, FormParser
from home.serializers import HomeSliderSerializer
from rest_framework.decorators import action
from django.http import FileResponse, Http404
import os
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import time 
import razorpay
from django.db import transaction
from decimal import Decimal
from utils.invoice_generator import generate_invoice_pdf
from rest_framework.decorators import api_view, permission_classes


logger = logging.getLogger(__name__)

def send_otp_sms(phone_number, otp):
    """
    Send OTP via SMS using Trygon SMS API
    """
    try:
        base_url = "https://sms.webtextsolution.com/sms-panel/api/http/index.php"
        
        # Prepare the message with OTP
        message = f"Dear User {otp} is the OTP for your login at Trygon. In case you have not requested this, please contact us at info@trygon.in"
        
        params = {
            'username': 'TRYGON',
            'apikey': 'E705A-DFEDC',
            'apirequest': 'Text',
            'sender': 'TRYGON', 
            'mobile': phone_number,
            'message': message,
            'route': 'TRANS',
            'TemplateID': '1707162192151162124',
            'format': 'JSON'
        }
        
        # Send the request with timeout
        response = requests.get(base_url, params=params, timeout=10)
        
        # Log the response
        logger.info(f"SMS API Response for {phone_number}: {response.text}")
        # Check if request was successful
        if response.status_code == 200:
            return True, "OTP sent successfully"
        else:
            logger.error(f"SMS API Error: {response.text}")
            return False, "Failed to send OTP"
            
    except requests.Timeout:
        logger.error(f"Timeout while sending OTP to {phone_number}")
        return False, "SMS service timeout"
    except Exception as e:
        logger.error(f"Error sending OTP to {phone_number}: {str(e)}")
        return False, str(e)

@method_decorator(csrf_exempt, name='dispatch')
class GenerateOTP(APIView):
    permission_classes = [AllowAny]

    def validate_phone_number(self, phone_number):
        """Validate phone number format"""
        if not phone_number:
            return False, "Phone number is required"
        if not phone_number.isdigit():
            return False, "Phone number should contain only digits"
        if not (10 <= len(phone_number) <= 12):
            return False, "Phone number should be 10-12 digits long"
        return True, "Valid phone number"

    def post(self, request):
        phone_number = request.data.get('phone_number')

        # Validate phone number
        is_valid, message = self.validate_phone_number(phone_number)
        if not is_valid:
            return Response({
                'status': False,
                'message': message
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if user exists and is not a customer
            user = User.objects.filter(phone_number=phone_number).first()
            if user and user.role != 'CUSTOMER':
                return Response({
                    'status': False,
                    'message': 'This number is registered as a non-customer user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Generate 6 digit OTP
            otp = str(random.randint(100000, 999999))

            # Save or update OTP
            phone_otp, created = PhoneOTP.objects.get_or_create(
                phone_number=phone_number,
                defaults={'otp': otp}
            )

            if not created:
                # Check if blocked period has expired
                phone_otp.reset_if_expired()
                
                # Check if still blocked
                if phone_otp.is_blocked():
                    minutes_left = 30 - ((timezone.now() - phone_otp.last_attempt).seconds // 60)
                    return Response({
                        'status': False,
                        'message': f'Maximum OTP attempts reached. Please try again after {minutes_left} minutes.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                phone_otp.otp = otp
                phone_otp.is_verified = False
                phone_otp.count += 1
                phone_otp.save()

            # Send OTP via SMS
            success, message = send_otp_sms(phone_number, otp)

            if success:
                return Response({
                    'status': True,
                    'message': 'OTP sent successfully',
                    'attempts_left': 5 - phone_otp.count,
                    'otp': otp  # Remove in production
                })
            else:
                return Response({
                    'status': False,
                    'message': f'Failed to send OTP: {message}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Error in GenerateOTP: {str(e)}")
            return Response({
                'status': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class VerifyOTP(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        phone_number = request.data.get('phone_number')
        otp = request.data.get('otp')
        
        if not phone_number or not otp:
            return Response({
                'status': False,
                'message': 'Phone number and OTP are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            phone_otp = PhoneOTP.objects.get(
                phone_number=phone_number,
                otp=otp,
                is_verified=False
            )
            
            phone_otp.is_verified = True
            phone_otp.save()
            
            # Get or create user
            user, created = User.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    'username': f"C{phone_number}",
                    'role': 'CUSTOMER'
                }
            )
            
            
            # refresh = RefreshToken.for_user(user)
            # Serialize user data
            user_data = UserSerializer(user).data
            from rest_framework_simplejwt.tokens import RefreshToken
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'status': True,
                'message': 'OTP verified successfully',
                'token': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'role': user.role,
                'userinfo': user_data
            })
            
        except PhoneOTP.DoesNotExist:
            return Response({
                'status': False,
                'message': 'Invalid OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in VerifyOTP: {str(e)}")
            return Response({
                'status': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        



# ---------------------- user login logics ----------------

@method_decorator(csrf_exempt, name='dispatch')
class UserLogin(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        print( 'data' , username)
        print( 'data password' , password)
        if not username or not password:
            return Response({
                'status': False,
                'message': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try: 
            # Authenticate user
            user = authenticate(username=username, password=password)
            print( 'user' , user)
            if not user:
                return Response({
                    'status': False,
                    'message': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Check if user is customer (customers should use OTP login)
            if user.role == 'CUSTOMER':
                return Response({
                    'status': False,
                    'message': 'Please use phone number and OTP to login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if user is active
            if not user.is_active:
                return Response({
                    'status': False,
                    'message': 'Account is inactive. Please contact admin.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            from rest_framework_simplejwt.tokens import RefreshToken
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            # Get role specific data
            user_data = None

            response_data = {
                'status': True,
                'message': 'Login successful',
                'token': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'user_data': user_data
            }
            
            return Response(response_data)
            
        except Exception as e:
            print(f"Error during login: {str(e)}")
            return Response({
                'status': False,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class RefreshToken(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        refresh_token = request.data.get('refresh')
        
        if not refresh_token:
            return Response({
                'status': False,
                'message': 'Refresh token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            refresh = RefreshToken(refresh_token)
            
            return Response({
                'status': True,
                'message': 'Token refreshed successfully',
                'token': str(refresh.access_token)
            })
            
        except Exception as e:
            return Response({
                'status': False,
                'message': 'Invalid refresh token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        

# ------------------------- middelware code for frontend -----------------------

class ValidateTokenView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Token will only reach here if valid
            return Response({
                'status': True,
                'role': request.user.role,
                'username': request.user.username,
                'email': request.user.email
            })
        except Exception as e:
            return Response({
                'status': False,
                'message': str(e)
            }, status=status.HTTP_401_UNAUTHORIZED)

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            if response.status_code == 200:
                return Response({
                    'status': True,
                    'access': response.data['access']
                })
            return Response({
                'status': False,
                'message': 'Invalid refresh token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({
                'status': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        


# ------------------------- Home Slider code for frontend -----------------------

class HomeSliderViewSet(viewsets.ModelViewSet):
    queryset = HomeSlider.objects.all().order_by('order')
    serializer_class = HomeSliderSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = [JWTAuthentication]


    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]
    
    def create(self, request, *args, **kwargs):
        print("Create method called")
        print("Request data:", request.data)
        return super().create(request, *args, **kwargs)
    
    # def destroy(self, request, *args, **kwargs):
    #     print("Delete method called")
    #     print("kwargs:", kwargs)
    #     return super().destroy(request, *args, **kwargs)
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response([], status=status.HTTP_200_OK)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    


# ------------------------ Categories Code for frontend ------------------------
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = Category.objects.all()

        # Filter by Slug
        slug = self.request.query_params.get('slug', None)
        if slug:
            queryset = queryset.filter(slug=slug)

        return queryset
    
    def create(self, request, *args, **kwargs):
        try:
            print("Create method called")
            print("Request data:", request.data)
            
            # Create serializer with explicit data
            serializer = self.get_serializer(data={
                'name': request.data.get('name'),
                'description': request.data.get('description'),
                'image': request.data.get('image'),
                'is_active': request.data.get('is_active', True),
                'parent': request.data.get('parent')
            })
            
            if serializer.is_valid():
                # self.perform_create(serializer)
                # instance = self.perform_create(serializer)
                instance = serializer.save()
                print(f"Created category with slug: {instance.slug}")
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                print("Validation errors:", serializer.errors)
                return Response(
                    {'error': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            print("Error creating category:", str(e))
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['GET'])
    def products(self, request, pk=None):
        """Get all products belonging to a specific category by slug"""
        category_slug = self.request.query_params.get('slug', None)
        
        if category_slug:
            category = Category.objects.filter(slug=category_slug).first()
            if not category:
                return Response({"error": "Category not found"}, status=404)
            
            products = category.products.all()  # Fetch related products
            serializer = ProductSerializer(products, many=True)
            return Response(serializer.data)
        
        return Response({"error": "Slug is required"}, status=400)



# ------------------------ Product Code for frontend ------------------------

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]
    
    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        context = super().get_serializer_context()
        # Ensure request is included in context for generating absolute URLs
        context['request'] = self.request
        return context
    

    def list(self, request, *args, **kwargs):
        """
        List products with additional debugging for brochure fields
        """
        print(f"Received request with params: {request.query_params}")
        queryset = self.filter_queryset(self.get_queryset())
        
        if 'slug' in request.query_params:
            slug = request.query_params.get('slug')
            print(f"Filtering by slug: {slug}")
            products = queryset.filter(slug=slug)
            print(f"Found {products.count()} products")
            for product in products:
                print(f"Product: {product.name}, Brochure: {product.product_brochure}")
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def get_queryset(self):
        queryset = Product.objects.all()

        # Filter by Slug
        slug = self.request.query_params.get('slug', None)
        if slug:
            queryset = queryset.filter(slug=slug)

        # Filter for trending products
        is_trending = self.request.query_params.get('trending', None)
        if is_trending:
            queryset = queryset.filter(is_trending=True)

        # Filter for featured products
        is_featured = self.request.query_params.get('featured', None)
        if is_featured:
            queryset = queryset.filter(is_featured=True)
        
        # Filter for bestseller products
        is_bestseller = self.request.query_params.get('bestseller', None)
        if is_bestseller:
            queryset = queryset.filter(is_bestseller=True)

        # Filter for new_arrival products
        is_new_arrival = self.request.query_params.get('new_arrival', None)
        if is_new_arrival:
            queryset = queryset.filter(is_new_arrival=True)

        return queryset

    @action(detail=True, methods=['DELETE'])
    def delete_image(self, request, slug=None):
        product = self.get_object()
        image_id = request.data.get('image_id')
        if image_id:
            image = get_object_or_404(ProductImage, id=image_id, product=product)
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['POST'])
    def set_feature_image(self, request, slug=None):
        product = self.get_object()
        image_id = request.data.get('image_id')
        if image_id:
            image = get_object_or_404(ProductImage, id=image_id, product=product)
            image.is_feature = True
            image.save()
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['GET'])
    def similar_products(self, request, slug=None):
        """Get similar products based on the same categories"""
        product = self.get_object()
        
        # Get categories of this product
        categories = product.categories.all()
        
        if not categories:
            return Response([])
        
        # Get products from the same categories, excluding this product
        similar_products = Product.objects.filter(
            categories__in=categories,
            is_active=True
        ).exclude(id=product.id).distinct()[:4]
        
        serializer = self.get_serializer(similar_products, many=True)
        return Response(serializer.data)

        
    @action(detail=True, methods=['GET'])
    def download_brochure(self, request, slug=None):
        """Download product brochure"""
        product = self.get_object()
        
        if not product.product_brochure:
            return Response(
                {'detail': 'No brochure available for this product'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            file_path = product.product_brochure.path
            
            if os.path.exists(file_path):
                response = FileResponse(
                    open(file_path, 'rb'),
                    content_type='application/pdf'
                )
                
                # Set the Content-Disposition header for download
                filename = os.path.basename(file_path)
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                
                return response
            else:
                raise Http404("Brochure file not found")
        except Exception as e:
            logger.error(f"Error downloading brochure: {str(e)}")
            return Response(
                {'detail': 'Error accessing brochure file'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    @action(detail=True, methods=['DELETE'])
    def remove_brochure(self, request, slug=None):
        """Remove product brochure"""
        product = self.get_object()
        
        if not product.product_brochure:
            return Response(
                {'detail': 'No brochure exists for this product'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Get the file path
            file_path = product.product_brochure.path
            
            # Remove file from storage if it exists
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Clear the field in the model
            product.product_brochure = None
            product.save()
            
            return Response(
                {'detail': 'Brochure removed successfully'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error removing brochure: {str(e)}")
            return Response(
                {'detail': 'Error removing brochure'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
       

class TestimonialViewSet(viewsets.ModelViewSet):
    queryset = Testimonial.objects.all()
    serializer_class = TestimonialSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = Testimonial.objects.all()
        if self.action == 'list':
            is_active = self.request.query_params.get('is_active')
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset.order_by('display_order', '-created_at')

    @action(detail=True, methods=['POST'])
    def toggle_status(self, request, pk=None):
        testimonial = self.get_object()
        testimonial.is_active = not testimonial.is_active
        testimonial.save()
        return Response({
            'status': 'success',
            'is_active': testimonial.is_active
        })

    @action(detail=True, methods=['POST'])
    def reorder(self, request, pk=None):
        testimonial = self.get_object()
        new_order = request.data.get('new_order')
        
        if new_order is None:
            return Response(
                {'error': 'New order is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        testimonial.display_order = new_order
        testimonial.save()
        return Response({'status': 'success'})
    

class AdvertisementViewSet(viewsets.ModelViewSet):
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = Advertisement.objects.all()
        if self.action == 'list':
            # Get filter parameters
            position = self.request.query_params.get('position')
            ad_type = self.request.query_params.get('type')
            is_active = self.request.query_params.get('is_active')
            
            # Apply filters if parameters are provided
            if position:
                queryset = queryset.filter(position=position)
            
            if ad_type:
                queryset = queryset.filter(type=ad_type)
                
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
                
        return queryset.order_by('-created_at')

    @action(detail=True, methods=['POST'])
    def toggle_status(self, request, pk=None):
        advertisement = self.get_object()
        advertisement.is_active = not advertisement.is_active
        advertisement.save()
        return Response({
            'status': 'success',
            'is_active': advertisement.is_active
        })
    
class ClientsViewSet(viewsets.ModelViewSet):
    queryset = Clients.objects.all()
    serializer_class = ClientsSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = Clients.objects.all()
        if self.action == 'list':
            position = self.request.query_params.get('position')
            is_active = self.request.query_params.get('is_active')
            
            if position:
                queryset = queryset.filter(position=position)
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
                
        return queryset.order_by('-created_at')

    @action(detail=True, methods=['POST'])
    def toggle_status(self, request, pk=None):
        advertisement = self.get_object()
        advertisement.is_active = not advertisement.is_active
        advertisement.save()
        return Response({
            'status': 'success',
            'is_active': advertisement.is_active
        })
    
class CompanyInfoViewSet(viewsets.ModelViewSet):
    queryset = CompanyInfo.objects.all()
    serializer_class = CompanyInfoSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        return CompanyInfo.objects.all()

    def list(self, request, *args, **kwargs):
        company_info = CompanyInfo.get_info()
        serializer = self.get_serializer(company_info)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if CompanyInfo.objects.exists():
            return Response(
                {'detail': 'Company information already exists. Use PATCH to update.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def get_object(self):
        queryset = self.get_queryset()
        obj = queryset.first()
        if not obj:
            obj = CompanyInfo.get_info()
        return obj

    @action(detail=False, methods=['patch'])
    def update_logo(self, request):
        company = self.get_object()
        if 'logo' not in request.FILES:
            return Response(
                {'detail': 'No logo file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        company.logo = request.FILES['logo']
        company.save()
        serializer = self.get_serializer(company)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_background_images(self, request):
        company = self.get_object()
        if 'footer_bg_image' in request.FILES:
            company.footer_bg_image = request.FILES['footer_bg_image']
        if 'testimonial_bg_image' in request.FILES:
            company.testimonial_bg_image = request.FILES['testimonial_bg_image']
            
        company.save()
        serializer = self.get_serializer(company)
        return Response(serializer.data)
    
class AboutViewSet(viewsets.ModelViewSet):
    queryset = About.objects.all()
    serializer_class = AboutSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = About.objects.all()
        about_type = self.request.query_params.get('type', None)
        if about_type:
            queryset = queryset.filter(type=about_type)
        return queryset

    @action(detail=False, methods=['GET'])
    def home(self, request):
        """Get homepage about content"""
        try:
            about = About.objects.get(type='HOME', is_active=True)
            serializer = self.get_serializer(about)
            return Response(serializer.data)
        except About.DoesNotExist:
            return Response(
                {'detail': 'Homepage about content not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['GET'])
    def main(self, request):
        """Get main about page content"""
        try:
            about = About.objects.get(type='MAIN', is_active=True)
            serializer = self.get_serializer(about)
            return Response(serializer.data)
        except About.DoesNotExist:
            return Response(
                {'detail': 'Main about content not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['PATCH'])
    def toggle_status(self, request, pk=None):
        about = self.get_object()
        about.is_active = not about.is_active
        about.save()
        return Response({
            'status': 'success',
            'is_active': about.is_active
        })
    

class MenuViewSet(viewsets.ModelViewSet):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = Menu.objects.all()
        if self.action == 'list':
            # Only show active menu items by default
            is_active = self.request.query_params.get('is_active')
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset.order_by('position')

    @action(detail=True, methods=['POST'])
    def toggle_status(self, request, pk=None):
        menu_item = self.get_object()
        menu_item.is_active = not menu_item.is_active
        menu_item.save()
        serializer = self.get_serializer(menu_item)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'])
    def update_position(self, request, pk=None):
        menu_item = self.get_object()
        new_position = request.data.get('position')
        
        if new_position is None:
            return Response(
                {'detail': 'Position is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_position = int(new_position)
            if new_position < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Position must be a non-negative integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        menu_item.position = new_position
        menu_item.save()
        serializer = self.get_serializer(menu_item)
        return Response(serializer.data)


class CustomPageViewSet(viewsets.ModelViewSet):
    queryset = CustomPage.objects.filter(is_active=True)
    serializer_class = CustomPageSerializer
    lookup_field = 'slug'
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        queryset = CustomPage.objects.filter(is_active=True)
        location = self.request.query_params.get('location', None)
        
        if location == 'header':
            queryset = queryset.filter(show_in_header=True)
        elif location == 'footer':
            queryset = queryset.filter(show_in_footer=True)
            
        return queryset.order_by('order', 'title')
    


class BulkOrderRequestViewSet(viewsets.ModelViewSet):
    queryset = BulkOrderRequest.objects.all()
    serializer_class = BulkOrderRequestSerializer
    lookup_field = 'id'
    
    def get_permissions(self):
        if self.action in ['create', 'user_requests']:
            return [AllowAny()]
        return [IsAdminUser()]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bulk_order = serializer.save()
        
        # Calculate quotation immediately
        bulk_order.calculate_quotation()
        
        # Send email notification to admin
        self._send_admin_notification(bulk_order)
        
        # Send confirmation email to customer
        self._send_customer_confirmation(bulk_order)
        
        return Response(
            self.get_serializer(bulk_order).data,
            status=status.HTTP_201_CREATED
        )
    
    def _send_admin_notification(self, bulk_order):
        try:
            company_info = CompanyInfo.get_info()
            admin_email = company_info.email
            
            subject = f"New Bulk Order Request: {bulk_order.name}"
            message = f"""
            A new bulk order request has been received.
            
            Customer: {bulk_order.name}
            Email: {bulk_order.email}
            Phone: {bulk_order.phone}
            Company: {bulk_order.company_name or 'N/A'}
            
            Product: {bulk_order.product.name}
            Quantity: {bulk_order.quantity_required}
            
            Additional Notes: {bulk_order.additional_notes or 'None'}
            
            Please review this request in the admin panel.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Error sending admin notification: {str(e)}")
    
    def _send_customer_confirmation(self, bulk_order):
        try:
            subject = f"Your Quote Request - {bulk_order.product.name}"
            
            if bulk_order.is_processed and bulk_order.status == 'quoted':
                message = f"""
                Dear {bulk_order.name},
                
                Thank you for requesting a quote for {bulk_order.product.name}.
                
                Your quote has been processed:
                - Quantity: {bulk_order.quantity_required}
                - Price per unit: ₹{bulk_order.price_per_unit}
                - Total quote amount: ₹{bulk_order.total_price}
                
                Please review this quote. If you'd like to proceed with this order,
                please contact our sales team or place your order through your account.
                
                Thank you for your interest in our products.
                """
            else:
                message = f"""
                Dear {bulk_order.name},
                
                Thank you for requesting a quote for {bulk_order.product.name}.
                
                We have received your request for:
                - Quantity: {bulk_order.quantity_required} units
                
                Our team is reviewing your request and will get back to you shortly with pricing information.
                
                Thank you for your interest in our products.
                """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [bulk_order.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Error sending customer confirmation: {str(e)}")
    
    @action(detail=False, methods=['GET'])
    def user_requests(self, request):
        """Get all bulk order requests for the current user's email"""
        email = request.query_params.get('email')
        if not email:
            return Response(
                {'detail': 'Email parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = BulkOrderRequest.objects.filter(email=email).order_by('-created_at')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['POST'])
    def process_quotation(self, request, id=None):
        """Admin action to process a quotation manually"""
        bulk_order = self.get_object()
        
        # Get manual price if provided
        price_per_unit = request.data.get('price_per_unit')
        
        if price_per_unit:
            try:
                price_per_unit = float(price_per_unit)
                bulk_order.price_per_unit = price_per_unit
                bulk_order.total_price = price_per_unit * bulk_order.quantity_required
            except ValueError:
                return Response(
                    {'detail': 'Invalid price format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Use automated calculation
            bulk_order.calculate_quotation()
        
        bulk_order.status = 'quoted'
        bulk_order.is_processed = True
        bulk_order.save()
        
        # Send email to customer with quotation
        self._send_customer_confirmation(bulk_order)
        
        serializer = self.get_serializer(bulk_order)
        return Response(serializer.data)
    
    @action(detail=True, methods=['PATCH'])
    def update_status(self, request, id=None):
        """Update the status of a bulk order request"""
        bulk_order = self.get_object()
        
        # Get the new status from the request
        new_status = request.data.get('status')
        if not new_status:
            return Response(
                {'detail': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the status
        valid_statuses = ['pending', 'quoted', 'approved', 'rejected']
        if new_status not in valid_statuses:
            return Response(
                {'detail': f'Invalid status. Must be one of {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the status
        bulk_order.status = new_status
        bulk_order.save()
        
        # Send email notification to customer
        self._send_status_update_email(bulk_order)
        
        serializer = self.get_serializer(bulk_order)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'])
    def send_email(self, request, id=None):
        """Send an email to the customer about their quotation"""
        bulk_order = self.get_object()
        
        # Send email based on the current status
        if bulk_order.status == 'pending':
            subject = f"Your Quotation Request - {bulk_order.product.name}"
            message = f"""
            Dear {bulk_order.name},
            
            Thank you for your quotation request for {bulk_order.product.name}.
            
            We are currently reviewing your request for {bulk_order.quantity_required} units and will get back to you shortly with pricing information.
            
            Best regards,
            Your Company Name
            """
        elif bulk_order.status == 'quoted':
            subject = f"Your Price Quote - {bulk_order.product.name}"
            message = f"""
            Dear {bulk_order.name},
            
            We are pleased to provide you with a quote for your request:
            
            Product: {bulk_order.product.name}
            Quantity: {bulk_order.quantity_required} units
            Price per unit: ₹{bulk_order.price_per_unit}
            Total price: ₹{bulk_order.total_price}
            
            This quote is valid for 7 days. To proceed with this order, please reply to this email or contact our sales team.
            
            Best regards,
            Your Company Name
            """
        elif bulk_order.status == 'approved':
            subject = f"Your Quotation Has Been Approved - {bulk_order.product.name}"
            message = f"""
            Dear {bulk_order.name},
            
            We are pleased to inform you that your quotation has been approved:
            
            Product: {bulk_order.product.name}
            Quantity: {bulk_order.quantity_required} units
            Price per unit: ₹{bulk_order.price_per_unit}
            Total price: ₹{bulk_order.total_price}
            
            Our team will contact you shortly to proceed with the order.
            
            Best regards,
            Your Company Name
            """
        elif bulk_order.status == 'rejected':
            subject = f"Update on Your Quotation Request - {bulk_order.product.name}"
            message = f"""
            Dear {bulk_order.name},
            
            Thank you for your interest in our products. 
            
            We regret to inform you that we are unable to provide a quotation for your request at this time. This may be due to availability, quantity constraints, or other factors.
            
            Please feel free to contact us to discuss alternative options or to submit a revised request.
            
            Best regards,
            Your Company Name
            """
        else:
            return Response(
                {'detail': 'Invalid status for sending email'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get company info for from_email
            company_info = CompanyInfo.get_info()
            from_email = settings.DEFAULT_FROM_EMAIL or company_info.email
            
            # Send the email
            send_mail(
                subject,
                message,
                from_email,
                [bulk_order.email],
                fail_silently=False,
            )
            
            return Response({'status': 'Email sent successfully'})
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return Response(
                {'detail': f'Error sending email: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _send_status_update_email(self, bulk_order):
        """Helper method to send status update emails"""
        try:
            # Get company info for from_email
            company_info = CompanyInfo.get_info()
            from_email = settings.DEFAULT_FROM_EMAIL or company_info.email
            
            if bulk_order.status == 'quoted':
                subject = f"Price Quote Ready - {bulk_order.product.name}"
                message = f"""
                Dear {bulk_order.name},
                
                Your quotation is ready:
                
                Product: {bulk_order.product.name}
                Quantity: {bulk_order.quantity_required} units
                Price per unit: ₹{bulk_order.price_per_unit}
                Total price: ₹{bulk_order.total_price}
                
                This quote is valid for 7 days. To proceed with this order, please contact our sales team.
                
                Best regards,
                Your Company Name
                """
            elif bulk_order.status == 'approved':
                subject = f"Your Quotation Has Been Approved - {bulk_order.product.name}"
                message = f"""
                Dear {bulk_order.name},
                
                We are pleased to inform you that your quotation has been approved. Our team will contact you shortly to proceed with the order.
                
                Best regards,
                Your Company Name
                """
            elif bulk_order.status == 'rejected':
                subject = f"Update on Your Quotation Request - {bulk_order.product.name}"
                message = f"""
                Dear {bulk_order.name},
                
                Thank you for your interest in our products. We regret to inform you that we are unable to provide a quotation for your request at this time.
                
                Please feel free to contact us to discuss alternative options.
                
                Best regards,
                Your Company Name
                """
            else:
                # Don't send emails for other statuses
                return
            
            # Send the email
            send_mail(
                subject,
                message,
                from_email,
                [bulk_order.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Error sending status update email: {str(e)}")



class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # If this is the user's first address, make it default
        if not Address.objects.filter(user=self.request.user).exists():
            serializer.save(user=self.request.user, is_active=True)
        else:
            serializer.save(user=self.request.user)

    @action(detail=True, methods=['POST'])
    def set_default(self, request, pk=None):
        address = self.get_object()
        # Set all other addresses to non-default
        Address.objects.filter(user=request.user).update(is_active=False)
        # Set this address as default
        address.is_active = True
        address.save()
        return Response({'status': 'default address set'})

    @action(detail=False, methods=['GET'])
    def default(self, request):
        address = Address.objects.filter(user=request.user, is_active=True).first()
        if address:
            serializer = self.get_serializer(address)
            return Response(serializer.data)
        return Response({'message': 'No default address found'}, 
                       status=status.HTTP_404_NOT_FOUND)

class CustomerProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Update customer profile"""
        if request.user.role != 'CUSTOMER':
            return Response({
                'status': 'error',
                'message': 'Only customers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = CustomerProfileSerializer(
            request.user, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                return Response({
                    'status': 'success',
                    'message': 'Profile updated successfully',
                    # 'user': CustomerProfileSerializer(user).data,
                    'userinfo': serializer.data 
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'status': 'error',
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    


# --------------------------------------------- Payment Secton --------------------------


class CreateOrderView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated] 
    def post(self, request):
        try:
            # Initialize Razorpay client
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )

            # Create Razorpay order
            data = {
                'amount': int(request.data.get('amount')) * 100,  # Amount in paise
                'currency': 'INR',
                'receipt': f'order_rcptid_{int(time.time())}',
                'payment_capture': 1  # Auto-capture payment
            }
            
            order = client.order.create(data=data)
            print('order' , order)
            print('data' , request.data)
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency']
            })
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class VerifyPaymentView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Log the incoming request data
            logger.info(f"Verify Payment Request Data: {request.data}")

            # Get payment details
            payment_id = request.data.get('razorpay_payment_id')
            order_id = request.data.get('razorpay_order_id')
            signature = request.data.get('razorpay_signature')
            update_stock = request.data.get('update_stock', False)

            # Additional logging
            logger.info(f"Payment ID: {payment_id}")
            logger.info(f"Order ID: {order_id}")

            # Get the order
            order = Order.objects.get(razorpay_order_id=order_id)

            # Initialize Razorpay client
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )

            # Verify signature
            params_dict = {
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': order_id,
                'razorpay_signature': signature
            }
            
            try:
                client.utility.verify_payment_signature(params_dict)
                
                # Use a transaction to ensure consistency
                with transaction.atomic():
                    # Update order status
                    order.status = 'CONFIRMED'
                    order.payment_id = payment_id
                    order.save()

                    # Update product stock if requested
                    if update_stock:
                        for item in order.items.all():
                            product = item.product
                            if product.stock >= item.quantity:
                                product.stock -= item.quantity
                                product.save()
                                logger.info(f"Updated stock for product {product.id}, new stock: {product.stock}")
                            else:
                                logger.warning(f"Insufficient stock for product {product.id}: requested {item.quantity}, available {product.stock}")
                                # We still proceed with the order even if stock is insufficient
                                # This is to avoid issues with the customer who already paid
                                product.stock = 0  # Set to zero instead of negative
                                product.save()

                return Response({
                    'status': 'success',
                    'message': 'Payment verified successfully',
                    'order_id': order.id
                })
            except Exception as e:
                order.status = 'FAILED'
                order.save()
                raise e

        except Exception as e:
            logger.error(f"Error in VerifyPaymentView: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
        
class OrderProcessView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def generate_order_number(self):
        return f"ORD-{int(time.time())}"
    
    
    
    def calculate_item_totals(self, product, quantity, discount_percentage=0):
        """Calculate totals for a single item with discount"""
        price = product.selling_price
        base_amount = price * quantity
        
        
            
        # Calculate GST on discounted amount
        gst_amount = (base_amount * product.gst_percentage) / 100
        total_price = base_amount + gst_amount
      
        
        return {
            'base_price': price,
            'gst_amount': gst_amount,
            'total_price': total_price,
        }
    
    def calculate_shipping(self, subtotal):
        """Calculate shipping cost based on subtotal"""
        return Decimal('0.00') if subtotal > 0 else Decimal('0.00')
    
    
    def post(self, request):
        try:
            # Get cart items (only need product IDs and quantities)
            cart_items = request.data.get('items', [])
            if not cart_items:
                return Response({
                    'status': 'error',
                    'message': 'Cart is empty'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get default address
            default_address = Address.objects.filter(
                user=request.user, 
                is_active=True
            ).first()
            
            if not default_address:
                return Response({
                    'status': 'error',
                    'message': 'No default address found'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get MLM discount percentage if applicable
            discount_percentage = 0
            
            # Initialize totals
            subtotal = Decimal('0.00')
            total_discount = Decimal('0.00')
            total_gst = Decimal('0.00')
            order_items = []

            # Calculate totals for each item
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['id'])
                    quantity = int(item['quantity'])

                    # Validate quantity
                    if quantity <= 0:
                        raise ValueError(f"Invalid quantity for product {product.name}")
                    if quantity > product.stock:
                        raise ValueError(f"Not enough stock for {product.name}")

                    # Calculate item totals with MLM discount if applicable
                    item_totals = self.calculate_item_totals(
                        product, 
                        quantity, 
                        discount_percentage
                    )
                    
                    subtotal += item_totals['base_price'] * quantity
                    total_discount += item_totals['discount_amount']
                    total_gst += item_totals['gst_amount']
                   

                    order_items.append({
                        'product': product,
                        'quantity': quantity,
                        'price': item_totals['base_price'],
                        'discount_amount': item_totals['discount_amount'],
                        'gst_amount': item_totals['gst_amount'],
                        'total_price': item_totals['total_price'],
                        
                    })

                except Product.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': f'Product with ID {item["id"]} not found'
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate shipping and final total
            shipping_cost = self.calculate_shipping(subtotal - total_discount)
            final_total = subtotal - total_discount + total_gst + shipping_cost

            # Create order
            order = Order.objects.create(
                user=request.user,
                order_number=self.generate_order_number(),
                total_amount=subtotal,
                discount_amount=total_discount,
                final_amount=final_total,
                shipping_address=f"{default_address.name}, {default_address.street_address}, {default_address.city}, {default_address.state}, {default_address.postal_code}",
                billing_address=f"{default_address.name}, {default_address.street_address}, {default_address.city}, {default_address.state}, {default_address.postal_code}",
                status='PENDING'
            )

            # Create order items
            for item in order_items:
                OrderItem.objects.create(
                    order=order,
                    product=item['product'],
                    quantity=item['quantity'],
                    price=item['price'],
                    discount_percentage=discount_percentage,
                    discount_amount=item['discount_amount'],
                    gst_amount=item['gst_amount'],
                    final_price=item['total_price'],
                    bp_points=item['bp_points']
                )


            # Create Razorpay order
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )

            payment_data = {
                'amount': int(final_total * 100),  # Convert to paise
                'currency': 'INR',
                'receipt': order.order_number,
                'payment_capture': 1,
                'notes': {
                    'order_id': order.id,
                    'shipping_address': order.shipping_address,
                }
            }
            
            razorpay_order = client.order.create(payment_data)
            
            # Update order with razorpay order id
            order.razorpay_order_id = razorpay_order['id']
            order.save()

            return Response({
                'status': 'success',
                'order_id': order.id,
                'razorpay_order_id': razorpay_order['id'],
                'amount': razorpay_order['amount'],
                'currency': razorpay_order['currency'],
                'order_summary': {
                    'subtotal': float(subtotal),
                    'discount': {
                        'percentage': float(discount_percentage),
                        'amount': float(total_discount)
                    },
                    'gst': float(total_gst),
                    'shipping': float(shipping_cost),
                    'total': float(final_total),
                }
            })

        except ValueError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Order processing error: {str(e)}")
            return Response({
                'status': 'error',
                'message': 'An unexpected error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateStockView(APIView):
    """
    API endpoint to update product stock after successful payment
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            items = request.data.get('items', [])
            
            if not items:
                return Response(
                    {'error': 'No items provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                updated_items = []
                out_of_stock_items = []
                
                for item in items:
                    product_id = item.get('product_id')
                    quantity = item.get('quantity', 0)
                    
                    try:
                        product = Product.objects.select_for_update().get(id=product_id)
                        
                        # Check if sufficient stock is available
                        if product.stock < quantity:
                            out_of_stock_items.append({
                                'product_id': product_id,
                                'name': product.name,
                                'available_stock': product.stock,
                                'requested_quantity': quantity
                            })
                            continue
                        
                        # Update the stock
                        product.stock -= quantity
                        product.save()
                        
                        updated_items.append({
                            'product_id': product_id,
                            'name': product.name,
                            'previous_stock': product.stock + quantity,
                            'new_stock': product.stock
                        })
                        
                    except Product.DoesNotExist:
                        return Response(
                            {'error': f'Product with ID {product_id} not found'}, 
                            status=status.HTTP_404_NOT_FOUND
                        )
                
                if out_of_stock_items:
                    # If any items are out of stock, rollback transaction and return error
                    transaction.set_rollback(True)
                    return Response({
                        'success': False,
                        'message': 'Some items are out of stock',
                        'out_of_stock_items': out_of_stock_items
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                return Response({
                    'success': True,
                    'message': 'Stock updated successfully',
                    'updated_items': updated_items
                })
                
        except Exception as e:
            logger.error(f"Error updating stock: {str(e)}")
            return Response(
                {'error': 'An error occurred while updating stock'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class CheckStockAvailabilityView(APIView):
    """
    API endpoint to check if requested products are in stock
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            items = request.data.get('items', [])
            
            if not items:
                return Response(
                    {'success': False, 'message': 'No items provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            out_of_stock_items = []
            
            for item in items:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 0)
                
                try:
                    product = Product.objects.get(id=product_id)
                    
                    # Check if sufficient stock is available
                    if product.stock < quantity:
                        out_of_stock_items.append({
                            'product_id': product_id,
                            'name': product.name,
                            'available_stock': product.stock,
                            'requested_quantity': quantity
                        })
                        
                except Product.DoesNotExist:
                    return Response(
                        {'success': False, 'message': f'Product with ID {product_id} not found'}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            if out_of_stock_items:
                return Response({
                    'success': False,
                    'message': 'Some items are out of stock',
                    'out_of_stock_items': out_of_stock_items
                })
            
            return Response({
                'success': True,
                'message': 'All items are in stock'
            })
            
        except Exception as e:
            logger.error(f"Error checking stock availability: {str(e)}")
            return Response(
                {'success': False, 'message': 'An error occurred while checking stock'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class OrderCancellationView(APIView):
    """
    API endpoint to cancel an incomplete order
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
            
            # Only allow cancellation for pending orders
            if order.status != 'PENDING':
                return Response(
                    {'error': 'Only pending orders can be cancelled'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update order status
            order.status = 'CANCELLED'
            order.save()
            
            return Response({
                'success': True,
                'message': 'Order cancelled successfully'
            })
            
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found or you do not have permission to cancel it'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error cancelling order: {str(e)}")
            return Response(
                {'error': 'An error occurred while cancelling the order'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
#----------------- Download Invoice ---------------------------------#



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_invoice(request, order_id):
    try:
        # For admin, allow access to any order
        if request.user.role == 'ADMIN':
            order = get_object_or_404(Order, id=order_id)
        else:
            # For regular users, only allow their own orders
            order = get_object_or_404(Order, id=order_id, user=request.user)
        
        # Generate PDF
        pdf_buffer = generate_invoice_pdf(order)
        
        # Create the response
        response = FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=f'invoice-{order.order_number}.pdf',
            content_type='application/pdf'
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Invoice download error for order {order_id}: {str(e)}")
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            user=self.request.user
        ).order_by('-order_date').select_related(
            'user'
        ).prefetch_related(
            'items',
            'items__product'
        )
    
