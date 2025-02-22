
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Testimonial , HomeSlider , Category , ProductImage , ProductFeature , Product  , Advertisement ,  CompanyInfo , About , Menu , CustomPage , Clients
from appAuth.serializers import UserSerializer
from django.db import IntegrityError
from django.db.models import Sum, Avg, Count, Min, Max
from django.db.models.functions import TruncMonth, TruncDay, TruncYear, Extract
from django.db.models import F, Q , Count
import re
User = get_user_model()

class TestimonialSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = [
            'id', 'name', 'designation', 'content',
            'image_url', 'rating', 'display_order'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None
    
class ClientsSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Clients
        fields = [
            'id', 'title', 'position',
            'image_url', 'is_active'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

class HomeSliderSerializer(serializers.ModelSerializer):
    desktop_image = serializers.ImageField(required=True)
    mobile_image = serializers.ImageField(required=False, allow_null=True)
    class Meta:
        model = HomeSlider
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at' ]

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_feature', 'order']

class ProductFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFeature
        fields = ['id', 'title', 'content', 'order']

class CategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    features = ProductFeatureSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(max_length=1000000),
        write_only=True,
        required=False
    )
    # feature_list = serializers.ListField(
    #     child=serializers.DictField(),
    #     write_only=True,
    #     required=False
    # )
    feature_list = serializers.JSONField(required=False)
    slug = serializers.SlugField(read_only=True)
    categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Category.objects.all(),
        required=False
    )
    category_details = CategoryDetailSerializer(source='categories', many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'regular_price', 
                 'selling_price', 'gst_percentage', 'stock',
                 'is_featured', 'is_bestseller', 'is_new_arrival', 
                 'is_trending', 'is_active', 'images', 'features',
                 'uploaded_images', 'feature_list', 'categories', 'category_details']
        # read_only_fields = ['slug']  # Make sure slug is read-only
        

    def validate(self, data):
        # Add proper validation messages
        if not data.get('name'):
            raise serializers.ValidationError({'name': 'Name is required'})
        
        # Generate slug from name
        from django.utils.text import slugify
        
        # Get the base slug from the name
        base_slug = slugify(data['name'])

        # Check if this slug already exists
        if Product.objects.filter(slug=base_slug).exists():
            # If it exists, append a number to make it unique
            count = 1
            while Product.objects.filter(slug=f"{base_slug}-{count}").exists():
                count += 1
            data['slug'] = f"{base_slug}-{count}"
        else:
            data['slug'] = base_slug
        return data
    
    def validate_feature_list(self, value):
        """
        Validate the feature list data
        """
        # If value is a string, try to parse it as JSON
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for feature_list")

        if not isinstance(value, list):
            raise serializers.ValidationError("Feature list must be an array")
        
        for feature in value:
            if not isinstance(feature, dict):
                raise serializers.ValidationError("Each feature must be an object")
            if 'title' not in feature or 'content' not in feature:
                raise serializers.ValidationError("Each feature must have title and content")
        return value
    

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        feature_list = validated_data.pop('feature_list', [])
        categories = validated_data.pop('categories', [])

        # If feature_list is a string, parse it
        # if isinstance(feature_list, str):
        #     import json
        #     feature_list = json.loads(feature_list)


        product = Product.objects.create(**validated_data)
        
        # Add categories
        if categories:
            product.categories.set(categories)


        # Create product features
        for idx, feature_data in enumerate(feature_list, 1):
            ProductFeature.objects.create(
                product=product,
                order=idx,
                # **feature_data
                title=feature_data.get('title', ''),
                content=feature_data.get('content', '')
            )
        
        # Create product images
        for idx, image in enumerate(uploaded_images):
            ProductImage.objects.create(
                product=product,
                image=image,
                order=idx + 1,
                is_feature=idx == 0  # First image is feature image
            )
        
        return product

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        feature_list = validated_data.pop('feature_list', [])
        categories = validated_data.pop('categories', None)


        # Update categories if provided
        if categories is not None:
            instance.categories.set(categories)


        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update features
        if feature_list:
            instance.features.all().delete()
            for idx, feature_data in enumerate(feature_list):
                ProductFeature.objects.create(
                    product=instance,
                    order=idx + 1,
                    **feature_data
                )
        
        # Add new images
        for idx, image in enumerate(uploaded_images):
            ProductImage.objects.create(
                product=instance,
                image=image,
                order=instance.images.count() + idx + 1
            )
        
        return instance
    

class CategorySerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at',  'slug']
        depth = 1
        


    def validate(self, data):
        # Add proper validation messages
        if not data.get('name'):
            raise serializers.ValidationError({'name': 'Name is required'})
        
        # Generate slug from name
        from django.utils.text import slugify
        
        # Get the base slug from the name
        base_slug = slugify(data['name'])

        # Check if this slug already exists
        if Category.objects.filter(slug=base_slug).exists():
            # If it exists, append a number to make it unique
            count = 1
            while Category.objects.filter(slug=f"{base_slug}-{count}").exists():
                count += 1
            data['slug'] = f"{base_slug}-{count}"
        else:
            data['slug'] = base_slug
        return data

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except Exception as e:
            print(f"Error in create: {str(e)}")
            raise


class TestimonialSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = [
            'id', 'name', 'designation', 'content', 
            'image', 'image_url', 'rating', 'is_active', 
            'display_order', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_image_url(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

class AdvertisementSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Advertisement
        fields = [
            'id', 'title', 'image', 'image_url', 'link', 
            'position', 'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None
    

class CompanyInfoSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    footer_bg_image_url = serializers.SerializerMethodField()
    testimonial_bg_image_url = serializers.SerializerMethodField()
    gst_state = serializers.SerializerMethodField()
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = CompanyInfo
        fields = [
            'id', 'company_name', 'logo', 'logo_url', 'gst_number', 'gst_state',
            'email', 'mobile_1', 'mobile_2', 'address_line1', 'address_line2',
            'city', 'state', 'pincode', 'country', 'facebook_link',
            'instagram_link', 'twitter_link', 'youtube_link', 'footer_bg_image',
            'footer_bg_image_url', 'testimonial_bg_image', 'testimonial_bg_image_url',
            'is_active', 'created_at', 'updated_at', 'full_address'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def get_footer_bg_image_url(self, obj):
        if obj.footer_bg_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.footer_bg_image.url)
        return None

    def get_testimonial_bg_image_url(self, obj):
        if obj.testimonial_bg_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.testimonial_bg_image.url)
        return None

    def get_gst_state(self, obj):
        return obj.get_gst_state()

    def validate_gst_number(self, value):
        if value:
            # Basic format check
            gst_pattern = r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}$'
            if not re.match(gst_pattern, value):
                raise serializers.ValidationError(
                    'Invalid GST format. Must be 15 characters long with pattern: 22AAAAA0000A1Z5'
                )
        return value


class AboutSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    left_image_url = serializers.SerializerMethodField()

    class Meta:
        model = About
        fields = [
            'id', 'type', 'type_display', 'title', 'content', 'feature_content',
            'left_image', 'left_image_url', 'vision_description', 
            'mission_description', 'objective_content', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_left_image_url(self, obj):
        if obj.left_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.left_image.url)
        return None

    def validate_type(self, value):
        instance = self.instance
        if instance is None:  # Creating new instance
            if About.objects.filter(type=value).exists():
                raise serializers.ValidationError(
                    f'An About page of type {value} already exists.'
                )
        elif instance.type != value:  # Updating existing instance
            if About.objects.filter(type=value).exists():
                raise serializers.ValidationError(
                    f'An About page of type {value} already exists.'
                )
        return value
    
class ProductListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'price', 'sale_price',
            'image', 'image_url', 'is_active',
            'is_trending', 'is_featured', 'is_new_arrival', 'is_bestseller'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None


class MenuSerializer(serializers.ModelSerializer):
    category_details = CategorySerializer(source='category', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Menu
        fields = [
            'id', 'category', 'category_details', 'category_name',
            'position', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_position(self, value):
        if value < 0:
            raise serializers.ValidationError("Position cannot be negative")
        return value


class CustomPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomPage
        fields = ['id', 'title', 'slug', 'content', 'is_active', 
                 'show_in_footer', 'show_in_header', 'order', 
                 'created_at', 'updated_at']