import re
import os
import random
import string
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import EmailValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db.models import Q , Max, F
from django.core.validators import MinLengthValidator
from django.urls import reverse

# ------------------------ Cusom User Model Area ------------------------------------
class CustomUserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required')
            
        user = self.model(username=username, **extra_fields)
        
        # Set default password for customers, actual password for others
        if extra_fields.get('role') == 'CUSTOMER':
            user.set_password('default123')  # Default password for customers
        else:
            if not password:
                raise ValueError('Password required for non-customer users')
            user.set_password(password)
            
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        return self.create_user(username, password, **extra_fields)

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        CUSTOMER = 'CUSTOMER', 'Customer'

    username = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone_number = models.CharField(max_length=10, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    
    objects = CustomUserManager()

    class Meta:
        db_table = 'users'
    def get_active_address(self):
        """Get the user's currently active address."""
        return self.addresses.filter(is_active=True).first()

    def set_active_address(self, address_id):
        """Set a specific address as active."""
        try:
            address = self.addresses.get(id=address_id)
            address.is_active = True
            address.save()
            return True
        except Address.DoesNotExist:
            return False

    def add_address(self, address_data):
        """Add a new address for the user."""
        if self.role not in ['CUSTOMER', 'ADMIN']:
            raise ValidationError("Only customers and MLM members can add addresses")
        
        address = Address.objects.create(
            user=self,
            **address_data
        )
        return address

# --------------------------------------Mulitple Address  -----------------------------------------

class Address(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='addresses')
    name = models.CharField(max_length=100, help_text="Name for this address (e.g. Home, Office)")
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_addresses'
        verbose_name_plural = 'Addresses'
        

    def save(self, *args, **kwargs):
        # If this address is being set as active
        if self.is_active:
            # Deactivate all other addresses for this user
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_active=False)
        
        # If this is the user's first address, make it active by default
        if not self.pk and not Address.objects.filter(user=self.user).exists():
            self.is_active = True

        super().save(*args, **kwargs)

    def clean(self):
        if self.user and self.user.role not in ['CUSTOMER']:
            raise ValidationError("Only customers and Admin can have addresses")

    def __str__(self):
        return f"{self.name} - {self.user.username}"




# --------------------------------------Phone OTp -----------------------------------------
class PhoneOTP(models.Model):
    phone_number = models.CharField(max_length=17)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    count = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)
    
    def is_blocked(self):
        if self.count >= 5:
            time_elapsed = timezone.now() - self.last_attempt
            return time_elapsed < timedelta(minutes=30)
        return False

    def reset_if_expired(self):
        if self.count >= 5:
            time_elapsed = timezone.now() - self.last_attempt
            if time_elapsed >= timedelta(minutes=30):
                self.count = 0
                self.save()

    class Meta:
        db_table = 'phone_otps'


#------------------------------------ Categoeis Model -----------------------------------------
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=150, unique=True , null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    show_in_home = models.BooleanField(default=False)
    class Meta:
        db_table = 'categories'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

# -------------------------------------------------- Product Model and featues -----------------------------
class ProductImage(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_feature = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_images'
        ordering = ['order']

    def save(self, *args, **kwargs):
        if self.is_feature:
            # Set all other images of this product to not feature
            ProductImage.objects.filter(product=self.product).exclude(id=self.id).update(is_feature=False)
        super().save(*args, **kwargs)

class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True)
    description = models.TextField()
    regular_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    categories = models.ManyToManyField(Category, related_name='products')
    stock = models.PositiveIntegerField(default=0)

    # GST field
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Homepage Display Fields
    is_featured = models.BooleanField(default=False, help_text="Show on homepage featured section")
    is_bestseller = models.BooleanField(default=False, help_text="Show in bestseller section")
    is_new_arrival = models.BooleanField(default=False, help_text="Show in new arrivals section")
    is_trending = models.BooleanField(default=False, help_text="Show in trending section")

    # Product Brochure
    product_brochure = models.FileField(
        upload_to='product/brochures/',
        blank=True,
        null=True,
        help_text="Upload product brochure in PDF format"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def discount_percentage(self):
        if self.regular_price > 0:
            discount = ((self.regular_price - self.selling_price) / self.regular_price) * 100
            return round(discount, 2)
        return 0

    @property
    def feature_image(self):
        return self.images.filter(is_feature=True).first() or self.images.first()

    def get_absolute_url(self):
        return f"/product/{self.slug}/"


class ProductFeature(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='features')
    title = models.CharField(max_length=200)
    content = models.TextField()
    order = models.PositiveIntegerField(default=1)
    
    class Meta:
        db_table = 'product_features'
        ordering = ['order']
    
    def __str__(self):
        return f"{self.product.name} - {self.title}"
    

class ProductFAQ(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='faq')
    title = models.CharField(max_length=200)
    content = models.TextField()
    order = models.PositiveIntegerField(default=1)
    
    class Meta:
        db_table = 'product_faq'
        ordering = ['order']
    
    def __str__(self):
        return f"{self.product.name} - {self.title}"
    

    
class Customer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer'
    )
    shipping_address = models.TextField()
    billing_address = models.TextField()

    class Meta:
        db_table = 'customers'



class BulkOrderRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('quoted', 'Quoted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_required = models.PositiveIntegerField()
    additional_notes = models.TextField(blank=True, null=True)

    # Pricing Details
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bulk Order - {self.name} ({self.email})"

    def calculate_quotation(self):
        """
        Calculates quotation using BulkOrderPrice.
        """
        bulk_price = BulkOrderPrice.objects.filter(
            product=self.product, 
            min_quantity__lte=self.quantity_required  # Find matching tier
        ).order_by('-min_quantity').first()  # Get the highest eligible tier

        # Default to selling price if no bulk pricing found
        price_per_unit = bulk_price.price_per_unit if bulk_price else self.product.selling_price
        total_price = price_per_unit * self.quantity_required

        # Save calculated price
        self.price_per_unit = price_per_unit
        self.total_price = total_price
        self.status = 'quoted'
        self.is_processed = True
        self.save()

class BulkOrderPrice(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bulk_prices')
    min_quantity = models.PositiveIntegerField()  # Minimum quantity for this price
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)  # Price for each unit at this tier

    class Meta:
        db_table = 'bulk_order_prices'
        ordering = ['min_quantity']  # Ensure lower quantities are checked first
        unique_together = ('product', 'min_quantity')  # Prevent duplicate entries

    def __str__(self):
        return f"{self.product.name} - {self.min_quantity}+ units @ ₹{self.price_per_unit} each"

# ------------------------------------------------------ Order Area --------------------------------------------------------
class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELLED = 'CANCELLED', 'Cancelled'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=50, unique=True)
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.TextField()
    billing_address = models.TextField()
    total_bp = models.PositiveIntegerField(default=0)  # Total BP points for the order

    class Meta:
        db_table = 'orders'

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    bp_points = models.PositiveIntegerField(default=0)  # BP points for this item

    class Meta:
        db_table = 'order_items'


# -------------------------------- Basic Webstie Functionality  -------------------------------------------------------------
class HomeSlider(models.Model):
    title = models.CharField(max_length=200)  # Added missing field
    desktop_image = models.ImageField(upload_to='slider/desktop/')
    mobile_image = models.ImageField(upload_to='slider/mobile/', null=True, blank=True)
    link = models.URLField(max_length=500)
    order = models.PositiveIntegerField(unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    class Meta:
        ordering = ['order']
        verbose_name = 'Home Slider'
        verbose_name_plural = 'Home Sliders'
        db_table = 'home_sliders'

    def clean(self):
        if not self.mobile_image and not self.desktop_image:
            raise ValidationError("At least one image (desktop or mobile) is required.")

    def save(self, *args, **kwargs):
        if not self.order:
            max_order = HomeSlider.objects.aggregate(Max('order'))['order__max']
            self.order = 1 if max_order is None else max_order + 1
        
        if HomeSlider.objects.filter(order=self.order).exclude(pk=self.pk).exists():
            HomeSlider.objects.filter(order__gte=self.order).exclude(pk=self.pk).update(
                order=F('order') + 1
            )
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Store paths before deletion
        desktop_path = self.desktop_image.path if self.desktop_image else None
        mobile_path = self.mobile_image.path if self.mobile_image else None
        
        # Call the parent delete method first
        super().delete(*args, **kwargs)
        
        # Delete files after model deletion
        if desktop_path and os.path.isfile(desktop_path):
            os.remove(desktop_path)
        if mobile_path and os.path.isfile(mobile_path):
            os.remove(mobile_path)

# Custom page 
class CustomPage(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=False)
    show_in_header = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'custom_pages'
        ordering = ['order', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/page/{self.slug}/"

# Blog page 
class Blog(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    feature_image = models.ImageField(upload_to='blogs/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    show_in_slider = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blog'
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    

class PageType(models.TextChoices):
    HOME = 'HOME', 'Home Page'
    ABOUT = 'ABOUT', 'About Page'
    CONTACT = 'CONTACT', 'Contact Page'
    PRODUCT = 'PRODUCT', 'Product Page'
    CATEGORY = 'CATEGORY', 'Category Page'
    CUSTOM = 'CUSTOM', 'Custom Page'
    BLOG = 'BLOG', 'Blog Page'



#  -------------------------------- Company Info Model ----------------------------------------

class CompanyInfo(models.Model):
    # Basic Info
    company_name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='company/')
    gst_number = models.CharField(max_length=15, blank=True)
    
    # Contact Details
    email = models.EmailField()
    mobile_1 = models.CharField(max_length=15)
    mobile_2 = models.CharField(max_length=15, blank=True)
    
    # Address
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='India')
    
    # Social Media Links
    facebook_link = models.URLField(blank=True)
    instagram_link = models.URLField(blank=True)
    twitter_link = models.URLField(blank=True)
    youtube_link = models.URLField(blank=True)
    
    # Company Profile PDF
    company_profile = models.FileField(
        upload_to='company/profiles/',
        blank=True,
        null=True,
        help_text="Upload company profile as a PDF file"
    )

    # Website Images
    footer_bg_image = models.ImageField(
        upload_to='company/backgrounds/', 
        blank=True,
        help_text="Background image for website footer"
    )
    testimonial_bg_image = models.ImageField(
        upload_to='company/backgrounds/',
        blank=True,
        help_text="Background image for testimonials section"
    )
    
    # Meta Information
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_info'
        verbose_name = 'Company Information'
        verbose_name_plural = 'Company Information'

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        # Ensure only one company info record exists
        if not self.pk and CompanyInfo.objects.exists():
            raise ValidationError('Only one company information record can exist.')
        return super().save(*args, **kwargs)

    @classmethod
    def get_info(cls):
        """Get company information - creates default if doesn't exist"""
        info, created = cls.objects.get_or_create(
            defaults={
                'company_name': 'Your Company Name',
                'email': 'info@yourcompany.com',
                'mobile_1': '+91 0000000000',
                'address_line1': 'Your Address',
                'city': 'Your City',
                'state': 'Your State',
                'pincode': '000000',
            }
        )
        return info

    @property
    def full_address(self):
        """Return formatted full address"""
        address_parts = [
            self.address_line1,
            self.address_line2,
            f"{self.city}, {self.state}",
            f"{self.pincode}",
            self.country
        ]
        return ', '.join(filter(None, address_parts))

    GST_STATE_CODES = {
        '01': 'Jammu & Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab',
        '04': 'Chandigarh', '05': 'Uttarakhand', '06': 'Haryana',
        '07': 'Delhi', '08': 'Rajasthan', '09': 'Uttar Pradesh',
        '10': 'Bihar', '11': 'Sikkim', '12': 'Arunachal Pradesh',
        '13': 'Nagaland', '14': 'Manipur', '15': 'Mizoram',
        '16': 'Tripura', '17': 'Meghalaya', '18': 'Assam',
        '19': 'West Bengal', '20': 'Jharkhand', '21': 'Odisha',
        '22': 'Chattisgarh', '23': 'Madhya Pradesh', '24': 'Gujarat',
        '26': 'Daman & Diu', '27': 'Maharashtra', '28': 'Andhra Pradesh',
        '29': 'Karnataka', '30': 'Goa', '31': 'Lakshadweep',
        '32': 'Kerala', '33': 'Tamil Nadu', '34': 'Puducherry',
        '35': 'Andaman & Nicobar Islands', '36': 'Telangana',
        '37': 'Andhra Pradesh (New)', '38': 'Ladakh'
    }

    def clean(self):
        if self.gst_number:
            # Basic format check
            gst_pattern = r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}$'
            if not re.match(gst_pattern, self.gst_number):
                raise ValidationError({
                    'gst_number': 'Invalid GST format. Must be 15 characters long with pattern: 22AAAAA0000A1Z5'
                })

            # State code validation
            state_code = self.gst_number[:2]
            if state_code not in self.GST_STATE_CODES:
                raise ValidationError({
                    'gst_number': f'Invalid state code {state_code}. Must be a valid Indian state code.'
                })

            # PAN validation (characters 3-12)
            pan_part = self.gst_number[2:12]
            pan_pattern = r'^[A-Z]{5}\d{4}[A-Z]{1}$'
            if not re.match(pan_pattern, pan_part):
                raise ValidationError({
                    'gst_number': 'Invalid PAN number format in GST.'
                })
        if self.company_profile:
            # Ensure only PDF files are uploaded
            if not self.company_profile.name.endswith('.pdf'):
                raise ValidationError({'company_profile': 'Only PDF files are allowed for company profile.'})

    def get_gst_state(self):
        """Returns the state name based on GST number"""
        if self.gst_number:
            state_code = self.gst_number[:2]
            return self.GST_STATE_CODES.get(state_code, 'Unknown State')



#--------------------------------- testimonials Model ----------------------------------------------------
class Testimonial(models.Model):
    name = models.CharField(
        max_length=100,
        validators=[MinLengthValidator(2, "Name must be at least 2 characters long")]
    )
    designation = models.CharField(
        max_length=100,
        help_text="Job title or role of the person"
    )
    content = models.TextField(
        validators=[MinLengthValidator(10, "Testimonial must be at least 10 characters long")]
    )
    image = models.ImageField(
        upload_to='testimonials/',
        help_text="Profile picture of the person",
        null=True,
        blank=True
    )
    rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(i, f"{i} Stars") for i in range(1, 6)]
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in which testimonials are displayed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'testimonials'
        ordering = ['display_order', '-created_at']
        verbose_name = 'Testimonial'
        verbose_name_plural = 'Testimonials'

    def __str__(self):
        return f"{self.name} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.display_order:
            # If no display order is set, put it at the end
            last_order = Testimonial.objects.aggregate(
                models.Max('display_order'))['display_order__max']
            self.display_order = (last_order or 0) + 1
        super().save(*args, **kwargs)

# ------------------------------ ads model -------------------------------------------------

class Advertisement(models.Model):
    TYPE_CHOICES = (
        ('MULTI', 'mulitple ads'),
        ('SINGLE', 'Full lenthg ad'),
        ('PRODUCT', 'PRO page ad')
    )
    title = models.CharField(max_length=200, blank=True, null=True)
    image = models.ImageField(upload_to='advertisements/')
    link = models.URLField(blank=True, null=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=7, choices=TYPE_CHOICES, default='MULTI')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'advertisements'
        ordering = ['-created_at']

    def __str__(self):
        return self.title
    
# ------------------------------ Our Clients model -------------------------------------------------

class Clients(models.Model):
    title = models.CharField(max_length=200, blank=True, null=True)
    image = models.ImageField(upload_to='clients/')
    position = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clients'
        ordering = ['-created_at']

    def __str__(self):
        return self.title if self.title else "Unnamed Client"
# ------------------------------------------- About model ---------------------------------------------------

class About(models.Model):
    TYPE_CHOICES = (
        ('HOME', 'Homepage About'),
        ('MAIN', 'Main About Page')
    )
    
    type = models.CharField(max_length=4, choices=TYPE_CHOICES, default='MAIN')
    title = models.CharField(max_length=200)
    content = models.TextField()
    feature_content = models.TextField(blank=True, null=True)
    left_image = models.ImageField(upload_to='about/')
    vision_description = models.TextField(blank=True, null=True)
    mission_description = models.TextField(blank=True, null=True)
    objective_content = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'about'
        verbose_name = 'About'
        verbose_name_plural = 'About'

    def __str__(self):
        return f"{self.get_type_display()} - {self.title}"

    def clean(self):
        # Check if another instance of the same type exists
        if not self.pk:
            if About.objects.filter(type=self.type).exists():
                raise ValidationError(f'An {self.get_type_display()} already exists.')
    

# -------------------------- Menu Model --------------------------------------------------------------------------------
class Menu(models.Model):
    category = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        related_name='menu_items'
    )
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menus'
        ordering = ['position']
        verbose_name = 'Menu'
        verbose_name_plural = 'Menu'

    def __str__(self):
        return self.category.name
# -------------------------------------------------------   MetaTags ---------------------------------------------------

class MetaTag(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    keywords = models.TextField(blank=True, help_text="Comma separated keywords")
    og_title = models.CharField(max_length=200, blank=True, verbose_name="Open Graph Title")
    og_description = models.TextField(blank=True, verbose_name="Open Graph Description")
    og_image = models.ImageField(upload_to='meta/og/', blank=True, verbose_name="Open Graph Image")
    twitter_title = models.CharField(max_length=200, blank=True)
    twitter_description = models.TextField(blank=True)
    twitter_image = models.ImageField(upload_to='meta/twitter/', blank=True)
    canonical_url = models.URLField(blank=True)
    
    # References to different page types
    page_type = models.CharField(max_length=20, choices=PageType.choices)
    product = models.OneToOneField('Product', on_delete=models.CASCADE, null=True, blank=True)
    category = models.OneToOneField('Category', on_delete=models.CASCADE, null=True, blank=True)
    custom_page = models.OneToOneField(CustomPage, on_delete=models.CASCADE, null=True, blank=True)
    blog = models.OneToOneField(Blog, on_delete=models.CASCADE, null=True, blank=True)
    is_default = models.BooleanField(default=False, help_text="Use as default meta for this page type")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meta_tags'
        constraints = [
            # Ensure only one default meta per page type
            models.UniqueConstraint(
                fields=['page_type', 'is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_meta_per_page_type'
            ),
            # Ensure only one reference is set
            models.CheckConstraint(
                check=(
                    models.Q(product__isnull=True, category__isnull=True, custom_page__isnull=True) |
                    models.Q(product__isnull=False, category__isnull=True, custom_page__isnull=True) |
                    models.Q(product__isnull=True, category__isnull=False, custom_page__isnull=True) |
                    models.Q(product__isnull=True, category__isnull=True, custom_page__isnull=False)
                ),
                name='only_one_reference_set'
            )
        ]

    def clean(self):
        # Validate that only one reference is set
        references = [
            bool(self.product),
            bool(self.category),
            bool(self.custom_page)
        ]
        if sum(references) > 1:
            raise ValidationError("Only one reference (product, category, or custom page) can be set.")
        
        # Validate default meta tags
        if self.is_default and (self.product or self.category or self.custom_page):
            raise ValidationError("Default meta tags cannot be linked to specific pages.")

    def __str__(self):
        if self.product:
            return f"Meta for Product: {self.product.name}"
        elif self.category:
            return f"Meta for Category: {self.category.name}"
        elif self.custom_page:
            return f"Meta for Page: {self.custom_page.title}"
        elif self.blog:
            return f"Meta for Page: {self.blog.title}"
        else:
            return f"Default Meta for {self.get_page_type_display()}"