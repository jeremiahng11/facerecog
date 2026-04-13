import json
import logging
import mimetypes
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


def parse_device(request) -> str:
    """
    Parse the User-Agent header into a human-readable device string
    like 'Android Mobile · Chrome' or 'macOS · Safari'.
    """
    import re
    ua = request.META.get('HTTP_USER_AGENT', '')
    if not ua:
        return 'Unknown'

    # ── Platform ──────────────────────────────────────────────────
    if 'iPhone' in ua:
        platform = 'iOS Mobile'
    elif 'iPad' in ua:
        platform = 'iOS Tablet'
    elif 'Android' in ua:
        platform = 'Android Mobile' if 'Mobile' in ua else 'Android Tablet'
    elif 'Windows' in ua:
        platform = 'Windows'
    elif 'Macintosh' in ua or 'Mac OS' in ua:
        platform = 'macOS'
    elif 'Linux' in ua:
        platform = 'Linux'
    elif 'CrOS' in ua:
        platform = 'Chrome OS'
    else:
        platform = 'Unknown OS'

    # ── Browser ───────────────────────────────────────────────────
    if 'Edg/' in ua or 'Edge/' in ua:
        browser = 'Edge'
    elif 'OPR/' in ua or 'Opera' in ua:
        browser = 'Opera'
    elif 'Firefox/' in ua:
        browser = 'Firefox'
    elif 'CriOS/' in ua or ('Chrome/' in ua and 'Safari/' in ua):
        browser = 'Chrome'
    elif 'Safari/' in ua and 'Chrome/' not in ua:
        browser = 'Safari'
    else:
        browser = 'Unknown Browser'

    return f'{platform} · {browser}'


def get_client_ip(request):
    """
    Return the real client IP address. Railway (and most reverse proxies)
    passes the original client IP in the X-Forwarded-For header. The
    header value is a comma-separated list where the first entry is the
    real client; subsequent entries are intermediate proxies.
    Falls back to REMOTE_ADDR when the header is absent (local dev).
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # First IP in the chain is the original client.
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


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
    registered face encodings. Requires multiple consecutive matches to
    the same user before granting login (prevents photo spoofing and
    cross-user false positives).

    The client tracks consecutive_match_user and consecutive_match_count
    and sends them back so the server can enforce the threshold.
    """
    try:
        data = json.loads(request.body)
        image_data = data.get('image')
        if not image_data:
            return JsonResponse({'success': False, 'message': 'No image received'})

        # Track consecutive matches sent by the client.
        client_match_user = data.get('match_user')       # staff_id
        client_match_count = data.get('match_count', 0)   # consecutive count

        required_consecutive = getattr(
            settings, 'FACE_VERIFY_CONSECUTIVE_MATCHES', 2
        )
        min_confidence = getattr(settings, 'FACE_MIN_CONFIDENCE', 65)

        # ── Face quality gate ──────────────────────────────────────
        # Reject frames where the face is too small, off-centre, or
        # not alone before spending CPU on encoding extraction.
        quality = face_utils.validate_face_quality(image_data)
        if not quality['ok']:
            return JsonResponse({
                'success': False,
                'message': quality['reason'],
                'face_detected': False,
                'match_user': None,
                'match_count': 0,
            })

        # Extract encoding from the live frame
        candidate_encoding = face_utils.extract_encoding_from_b64(image_data)
        if candidate_encoding is None:
            return JsonResponse({
                'success': False,
                'message': 'No face detected in frame. Please look at the camera.',
                'face_detected': False,
                'match_user': None,
                'match_count': 0,
            })

        # Compare against all users with face_enabled and registered encoding
        tolerance = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.4)
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
            result = face_utils.compare_faces(
                known_encoding, candidate_encoding, tolerance
            )
            if result['match'] and result['confidence'] > best_confidence:
                best_match = user
                best_confidence = result['confidence']

        ip_addr = get_client_ip(request)
        device_info = parse_device(request)

        if best_match and best_confidence >= min_confidence:
            # Count consecutive matches to the same user.
            if client_match_user == best_match.staff_id:
                consecutive = client_match_count + 1
            else:
                consecutive = 1

            if consecutive < required_consecutive:
                # Partial match — tell the client to keep going.
                return JsonResponse({
                    'success': False,
                    'face_detected': True,
                    'message': f'Verifying… ({consecutive}/{required_consecutive})',
                    'match_user': best_match.staff_id,
                    'match_count': consecutive,
                    'confidence': best_confidence,
                    'verifying': True,
                })

            # ── Enough consecutive matches — grant login ──────────────
            FaceLoginLog.objects.create(
                user=best_match,
                success=True,
                confidence=best_confidence,
                ip_address=ip_addr,
                device=device_info,
                notes=f'{required_consecutive} consecutive matches',
            )
            best_match.last_face_login = timezone.now()
            best_match.save(update_fields=['last_face_login'])

            login(request, best_match,
                  backend='django.contrib.auth.backends.ModelBackend')

            return JsonResponse({
                'success': True,
                'message': f'Welcome, {best_match.display_name}!',
                'confidence': best_confidence,
                'redirect': '/dashboard/',
                'match_user': None,
                'match_count': 0,
            })
        else:
            # No match or below confidence threshold — reset streak.
            FaceLoginLog.objects.create(
                success=False,
                ip_address=ip_addr,
                device=device_info,
                notes='No matching face found',
            )
            return JsonResponse({
                'success': False,
                'face_detected': True,
                'message': 'Face not recognised. Try again or use Staff ID login.',
                'confidence': 0,
                'match_user': None,
                'match_count': 0,
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
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = FacePhotoUploadForm(instance=user)
    context = {
        'form': form,
        'user': user,
        'enroll_num_samples': getattr(settings, 'FACE_ENROLL_NUM_SAMPLES', 5),
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
def my_face_photo_view(request):
    """
    Serve the current user's own face photo. This is the ONLY way to
    retrieve a face photo over HTTP — the generic /media/face_photos/
    route returns 404 unconditionally. Because this view reads
    request.user.face_photo, it is impossible for one user to fetch
    another user's biometric image.
    """
    user = request.user
    if not user.face_photo:
        from django.http import Http404
        raise Http404("No face photo on file")

    try:
        f = user.face_photo.open('rb')
        content_type = mimetypes.guess_type(user.face_photo.name)[0] or 'image/jpeg'
        from django.http import FileResponse
        response = FileResponse(f, content_type=content_type)
        # Prevent browser from caching the photo in shared caches.
        response['Cache-Control'] = 'private, no-store'
        return response
    except Exception:
        from django.http import Http404
        raise Http404("Face photo not accessible")


@login_required
@require_POST
def enroll_face_ajax(request):
    """
    AJAX: receive multiple captured webcam snapshots (base64 array),
    extract a jittered encoding from each, check for duplicates in the
    system, average them into a single robust template, and store it.
    """
    try:
        data = json.loads(request.body)
        images = data.get('images', [])

        # Accept a single image for backwards compat, but prefer array.
        if not images and data.get('image'):
            images = [data['image']]

        num_samples_required = getattr(settings, 'FACE_ENROLL_NUM_SAMPLES', 5)
        num_jitters = getattr(settings, 'FACE_ENROLL_NUM_JITTERS', 3)
        dup_tolerance = getattr(settings, 'FACE_ENROLL_DUPLICATE_TOLERANCE', 0.35)

        if len(images) < num_samples_required:
            return JsonResponse({
                'success': False,
                'message': f'Need {num_samples_required} captures, got {len(images)}.',
            })

        user = request.user
        encodings = []

        for idx, image_data in enumerate(images):
            # Validate face quality: one face, large enough, centred.
            quality = face_utils.validate_face_quality(image_data)
            if not quality['ok']:
                return JsonResponse({
                    'success': False,
                    'message': f'Capture {idx + 1}: {quality["reason"]}',
                })

            # Extract high-quality encoding with jitter
            enc = face_utils.extract_encoding_from_b64_jittered(
                image_data, num_jitters=num_jitters
            )
            if enc is None:
                return JsonResponse({
                    'success': False,
                    'message': f'Could not extract face data from capture {idx + 1}.',
                })
            encodings.append(enc)

        # Average all sample encodings into a single robust template.
        final_encoding = face_utils.average_encodings(encodings)

        # ── Duplicate face check ──────────────────────────────────────
        # Before enrolling, make sure this face is not too similar to
        # any existing enrolled user. This prevents cross-login between
        # people with similar features.
        dup = face_utils.check_duplicate_face(
            final_encoding,
            tolerance=dup_tolerance,
            exclude_user_pk=user.pk,
        )
        if dup:
            dup_user = dup['user']
            logger.warning(
                f"Enrollment rejected for {user.staff_id}: face too similar "
                f"to {dup_user.staff_id} (distance={dup['distance']})"
            )
            return JsonResponse({
                'success': False,
                'message': (
                    'Enrollment failed: your face is too similar to another '
                    'enrolled user. Please contact an administrator.'
                ),
            })

        # ── Save face photo ───────────────────────────────────────────
        # Use the first capture as the stored face_photo reference.
        filename = f"{user.staff_id}_face.jpg"
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = os.path.join(tmp_dir, filename)
            saved = face_utils.save_face_snapshot(images[0], save_path)
            if saved:
                with open(save_path, 'rb') as f:
                    user.face_photo.save(
                        f'face_photos/{filename}', DjangoFile(f), save=False
                    )

        user.set_face_encoding(final_encoding)
        user.face_registered = True
        user.face_enabled = True
        user.save(update_fields=[
            'face_photo', 'face_encoding', 'face_registered', 'face_enabled'
        ])

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
            user = form.save()
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
            form.save()
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
