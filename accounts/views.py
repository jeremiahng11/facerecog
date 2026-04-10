import json
import logging
import os
import tempfile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.files import File as DjangoFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings

from .models import StaffUser, FaceLoginLog
from .forms import StaffLoginForm, StaffUserCreationForm, StaffUserEditForm, FacePhotoUploadForm
from . import face_utils

logger = logging.getLogger(__name__)


def is_admin(user):
    return user.is_staff or user.is_superuser


# ─── Login / Logout ────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = StaffLoginForm(request.POST)
        if form.is_valid():
            staff_id = form.cleaned_data['staff_id']
            password = form.cleaned_data['password']
            user = authenticate(request, username=staff_id, password=password)
            if user is not None and user.is_active:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid Staff ID or Password.')
    else:
        form = StaffLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Face ID Login ─────────────────────────────────────────────────────────────

def face_login_view(request):
    """Render the face ID login page"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/face_login.html')


@require_POST
def face_verify_ajax(request):
    """
    AJAX endpoint: receive base64 frame from webcam, compare against all
    registered face encodings, return match result.
    """
    try:
        data = json.loads(request.body)
        image_data = data.get('image')
        if not image_data:
            return JsonResponse({'success': False, 'message': 'No image received'})

        # Extract encoding from the live frame
        candidate_encoding = face_utils.extract_encoding_from_b64(image_data)
        if candidate_encoding is None:
            return JsonResponse({
                'success': False,
                'message': 'No face detected in frame. Please look at the camera.',
                'face_detected': False,
            })

        # Compare against all users with face_enabled and registered encoding
        tolerance = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.5)
        users_with_face = StaffUser.objects.filter(
            face_enabled=True,
            face_registered=True,
            is_active=True
        ).exclude(face_encoding__isnull=True).exclude(face_encoding='')

        best_match = None
        best_confidence = 0.0

        for user in users_with_face:
            known_encoding = user.get_face_encoding()
            if not known_encoding:
                continue
            result = face_utils.compare_faces(known_encoding, candidate_encoding, tolerance)
            if result['match'] and result['confidence'] > best_confidence:
                best_match = user
                best_confidence = result['confidence']

        ip_addr = request.META.get('REMOTE_ADDR')

        if best_match:
            # Log success
            FaceLoginLog.objects.create(
                user=best_match,
                success=True,
                confidence=best_confidence,
                ip_address=ip_addr,
            )
            best_match.last_face_login = timezone.now()
            best_match.save(update_fields=['last_face_login'])

            # Log the user in
            login(request, best_match,
                  backend='django.contrib.auth.backends.ModelBackend')

            return JsonResponse({
                'success': True,
                'message': f'Welcome, {best_match.display_name}!',
                'confidence': best_confidence,
                'redirect': '/dashboard/',
            })
        else:
            FaceLoginLog.objects.create(
                success=False,
                ip_address=ip_addr,
                notes='No matching face found',
            )
            return JsonResponse({
                'success': False,
                'face_detected': True,
                'message': 'Face not recognised. Try again or use Staff ID login.',
                'confidence': 0,
            })

    except Exception as e:
        logger.exception("Error in face_verify_ajax")
        return JsonResponse({'success': False, 'message': f'Server error: {str(e)}'})


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    context = {
        'user': request.user,
        'face_enabled': request.user.face_enabled,
        'face_registered': request.user.face_registered,
    }
    return render(request, 'accounts/dashboard.html', context)


# ─── Profile / Face Enrolment ──────────────────────────────────────────────────

@login_required
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        form = FacePhotoUploadForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            saved_user = form.save(commit=False)
            # If a new face_photo was uploaded, re-extract encoding
            if 'face_photo' in request.FILES:
                saved_user.save()  # save first so the storage backend has the file
                encoding = face_utils.extract_encoding_from_field_file(saved_user.face_photo)
                if encoding:
                    saved_user.set_face_encoding(encoding)
                    saved_user.face_registered = True
                    messages.success(request, 'Face photo saved and face registered successfully!')
                else:
                    saved_user.face_registered = False
                    messages.warning(request,
                        'Photo saved but no face was detected. '
                        'Please upload a clear frontal face photo.')
                saved_user.save()
            else:
                saved_user.save()
                messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = FacePhotoUploadForm(instance=user)
    context = {
        'form': form,
        'user': user,
        'requirements': [
            'Good lighting',
            'Face clearly visible',
            'Look directly at camera',
            'Only one person in frame',
            'No heavy filters or masks',
        ],
    }
    return render(request, 'accounts/profile.html', context)


@login_required
@require_POST
def enroll_face_ajax(request):
    """
    AJAX: receive a captured webcam snapshot, save it as face_photo,
    extract and store the encoding.
    """
    try:
        data = json.loads(request.body)
        image_data = data.get('image')
        if not image_data:
            return JsonResponse({'success': False, 'message': 'No image data'})

        # Detect face first
        n_faces = face_utils.detect_faces_in_b64(image_data)
        if n_faces == 0:
            return JsonResponse({'success': False, 'message': 'No face detected. Please centre your face.'})
        if n_faces > 1:
            return JsonResponse({'success': False, 'message': 'Multiple faces detected. Please be alone in frame.'})

        # Save snapshot to a temporary local file for encoding extraction.
        # Using a temp directory means this works regardless of whether
        # MEDIA_ROOT is defined (it may not be when Cloudinary is active).
        user = request.user
        filename = f"{user.staff_id}_face.jpg"

        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = os.path.join(tmp_dir, filename)
            saved = face_utils.save_face_snapshot(image_data, save_path)
            if not saved:
                return JsonResponse({'success': False, 'message': 'Failed to save image.'})

            # Extract encoding from the local temp file
            encoding = face_utils.extract_encoding_from_file(save_path)
            if not encoding:
                return JsonResponse({'success': False, 'message': 'Could not extract face data.'})

            # Persist the photo via Django's storage backend (works for both
            # local filesystem and Cloudinary).
            with open(save_path, 'rb') as f:
                user.face_photo.save(f'face_photos/{filename}', DjangoFile(f), save=False)

        user.set_face_encoding(encoding)
        user.face_registered = True
        user.face_enabled = True
        user.save(update_fields=['face_photo', 'face_encoding', 'face_registered', 'face_enabled'])

        # Do NOT return face_photo.url — face photos are biometric data
        # and are never exposed over HTTP. The client only needs a
        # success signal to flip the enrolled badge.
        return JsonResponse({
            'success': True,
            'message': 'Face enrolled successfully! You can now use Face ID login.',
        })

    except Exception as e:
        logger.exception("Error in enroll_face_ajax")
        return JsonResponse({'success': False, 'message': str(e)})


# ─── Admin: User Management ────────────────────────────────────────────────────

@login_required
@user_passes_test(is_admin)
def admin_users_view(request):
    users = StaffUser.objects.all().order_by('-date_joined')
    return render(request, 'accounts/admin_users.html', {'users': users})


@login_required
@user_passes_test(is_admin)
def admin_add_user_view(request):
    if request.method == 'POST':
        form = StaffUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            # If face photo provided, extract encoding
            if user.face_photo:
                user.save()  # save so the storage backend has the file
                encoding = face_utils.extract_encoding_from_field_file(user.face_photo)
                if encoding:
                    user.set_face_encoding(encoding)
                    user.face_registered = True
                    messages.success(request,
                        f'User {user.staff_id} created with face registration!')
                else:
                    messages.warning(request,
                        f'User {user.staff_id} created but no face detected in photo.')
                user.save()
            else:
                user.save()
                messages.success(request, f'User {user.staff_id} created successfully.')
            return redirect('admin_users')
    else:
        form = StaffUserCreationForm()
    return render(request, 'accounts/admin_add_user.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def admin_edit_user_view(request, user_id):
    target_user = get_object_or_404(StaffUser, pk=user_id)
    if request.method == 'POST':
        form = StaffUserEditForm(request.POST, request.FILES, instance=target_user)
        if form.is_valid():
            user = form.save(commit=False)
            if 'face_photo' in request.FILES:
                user.save()
                encoding = face_utils.extract_encoding_from_field_file(user.face_photo)
                if encoding:
                    user.set_face_encoding(encoding)
                    user.face_registered = True
                    messages.success(request, 'User updated with new face registration.')
                else:
                    user.face_registered = False
                    messages.warning(request, 'User updated but face not detected in photo.')
                user.save()
            else:
                user.save()
                messages.success(request, 'User updated successfully.')
            return redirect('admin_users')
    else:
        form = StaffUserEditForm(instance=target_user)
    return render(request, 'accounts/admin_edit_user.html', {
        'form': form,
        'target_user': target_user,
    })


@login_required
@user_passes_test(is_admin)
def admin_delete_user_view(request, user_id):
    target_user = get_object_or_404(StaffUser, pk=user_id)
    if request.method == 'POST':
        name = target_user.staff_id
        target_user.delete()
        messages.success(request, f'User {name} deleted.')
        return redirect('admin_users')
    return render(request, 'accounts/admin_confirm_delete.html', {'target_user': target_user})


@login_required
@user_passes_test(is_admin)
def admin_face_logs_view(request):
    logs = FaceLoginLog.objects.all().select_related('user')[:200]
    return render(request, 'accounts/admin_face_logs.html', {'logs': logs})


# ─── Re-enroll face for a specific user (admin) ───────────────────────────────

@login_required
@user_passes_test(is_admin)
@require_POST
def admin_reencode_user(request, user_id):
    target_user = get_object_or_404(StaffUser, pk=user_id)
    if target_user.face_photo:
        encoding = face_utils.extract_encoding_from_field_file(target_user.face_photo)
        if encoding:
            target_user.set_face_encoding(encoding)
            target_user.face_registered = True
            target_user.save()
            messages.success(request, f'Face re-encoded for {target_user.staff_id}.')
        else:
            messages.error(request, 'No face detected in existing photo.')
    else:
        messages.error(request, 'No face photo on file.')
    return redirect('admin_edit_user', user_id=user_id)
