from django.contrib import admin
from django.utils.html import format_html
# Register your models here.
from .models import (
    User, PhoneOTP, Product, Customer, Order, OrderItem,
    Testimonial , Advertisement , About ,Menu ,CompanyInfo, CustomPage
)

# Register your models here.
admin.site.register(User)
admin.site.register(PhoneOTP)
admin.site.register(Product)
admin.site.register(Customer)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(CompanyInfo)
admin.site.register(CustomPage)

from django.utils.html import format_html

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'designation', 'rating', 'image_preview', 'is_active', 'display_order']
    list_editable = ['is_active', 'display_order']
    list_filter = ['is_active', 'rating']
    search_fields = ['name', 'designation', 'content']
    readonly_fields = ['image_preview']
    ordering = ['display_order']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 50px; max-height: 50px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Image Preview'


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ['title', 'image_preview', 'position', 'is_active']
    list_editable = ['is_active']
    search_fields = ['title', 'position']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Image Preview'


@admin.register(About)
class AboutAdmin(admin.ModelAdmin):
    list_display = ['title', 'type', 'image_preview', 'is_active']
    list_editable = ['is_active']
    readonly_fields = ['image_preview']
    
    # Show/hide fields based on type
    def get_fieldsets(self, request, obj=None):
        if obj and obj.type == 'HOME' or request.GET.get('type') == 'HOME':
            return (
                (None, {
                    'fields': ('type', 'title', 'content', 'feature_content', 
                             'left_image', 'image_preview', 'is_active')
                }),
            )
        return (
            (None, {
                'fields': ('type', 'title', 'content', 'left_image', 
                         'image_preview', 'vision_description', 
                         'mission_description', 'objective_content', 'is_active')
            }),
        )

    def image_preview(self, obj):
        if obj.left_image:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.left_image.url
            )
        return "No image"
    image_preview.short_description = 'Image Preview'

    def get_form(self, request, obj=None, **kwargs):
        # Pre-set the type for new instances based on URL parameter
        form = super().get_form(request, obj, **kwargs)
        if not obj and 'type' in request.GET:
            form.base_fields['type'].initial = request.GET['type']
        return form
    
@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ['category', 'position', 'is_active']
    list_editable = ['position', 'is_active']