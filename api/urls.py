
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path , include
from rest_framework.routers import DefaultRouter
from appAuth.views import GenerateOTP , VerifyOTP , UserLogin , RefreshToken , ValidateTokenView , CustomTokenRefreshView , HomeSliderViewSet , CategoryViewSet , ProductViewSet   , TestimonialViewSet , AdvertisementViewSet  , CompanyInfoViewSet , AboutViewSet  , MenuViewSet , CustomPageViewSet , ClientsViewSet , BulkOrderRequestViewSet , AddressViewSet , CustomerProfileView , CreateOrderView , VerifyPaymentView , OrderProcessView , UpdateStockView , CheckStockAvailabilityView , OrderCancellationView , download_invoice , OrderViewSet


router = DefaultRouter()
router.register(r'home-sliders', HomeSliderViewSet, basename='home-slider')
router.register(r'categories', CategoryViewSet , basename='category')
router.register(r'products', ProductViewSet , basename='products')
router.register(r'testimonials', TestimonialViewSet , basename='testimonials')
router.register(r'advertisements', AdvertisementViewSet , basename='advertisements')
router.register(r'company-info', CompanyInfoViewSet , basename='company-info')
router.register(r'about', AboutViewSet, basename='about')
router.register(r'menu', MenuViewSet, basename='menu')
router.register(r'custom-pages', CustomPageViewSet , basename='custom-pages')
router.register(r'clients', ClientsViewSet , basename='clients')
router.register(r'bulk-order-requests', BulkOrderRequestViewSet, basename='bulk-order-requests')
router.register(r'addresses', AddressViewSet , basename='addresses')
router.register(r'allorders', OrderViewSet, basename='allorders')


urlpatterns = [

    path('generate-otp/', GenerateOTP.as_view(), name='generate-otp'),
    path('verify-otp/', VerifyOTP.as_view(), name='verify-otp'),


    #home slider url
    path('', include(router.urls)),

    # Username/password routes for MLM members and admin
    path('login/', UserLogin.as_view(), name='user-login'),
    path('refresh-token/', RefreshToken.as_view(), name='refresh-token'),


    # For middelware
    path('validate-token/', ValidateTokenView.as_view(), name='validate-token'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),

    path('profile/details/', CustomerProfileView.as_view(), name='customer-profile-details'),
    path('profile/update/', CustomerProfileView.as_view(), name='customer-profile-update'),


    path('create-order/', CreateOrderView.as_view(), name='create_order'),
    path('verify-payment/', VerifyPaymentView.as_view(), name='verify_payment'),

    path('orders/create/', OrderProcessView.as_view(), name='create-order'),
    path('orders/<int:order_id>/invoice/', download_invoice, name='download-invoice'),

    path('update-stock/', UpdateStockView.as_view(), name='update-stock'),
    path('check-stock/', CheckStockAvailabilityView.as_view(), name='check-stock'),
    path('orders/<int:order_id>/cancel/', OrderCancellationView.as_view(), name='cancel-order'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)