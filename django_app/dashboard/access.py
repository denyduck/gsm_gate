from django.db.models import Q

from .models import AutomationRule, DeviceObject, Group, PhoneNumber, UserGroupVisibilityOverride


def get_accessible_groups_qs(user):
    if user is None or not user.is_authenticated:
        return Group.objects.none()

    if user.is_superuser:
        return Group.objects.all()

    django_group_names = user.groups.values_list('name', flat=True)

    return Group.objects.filter(
        Q(owner=user) | Q(users=user) | Q(name__in=django_group_names)
    ).distinct()


def get_accessible_numbers_qs(user, active_only=False):
    if user is None or not user.is_authenticated:
        return PhoneNumber.objects.none()

    if user.is_superuser:
        queryset = PhoneNumber.objects.all()
        if active_only:
            queryset = queryset.filter(active=True)
        return queryset

    direct_queryset = PhoneNumber.objects.filter(
        Q(owner=user)
        | Q(users=user)
        | Q(groups__users=user)
    ).distinct()

    accessible_groups = get_accessible_groups_qs(user)
    inherited_queryset = PhoneNumber.objects.filter(groups__in=accessible_groups).distinct()

    hidden_ids = set(
        UserGroupVisibilityOverride.objects.filter(
            user=user,
            group__in=accessible_groups,
        ).values_list('hidden_numbers__id', flat=True)
    )
    hidden_ids.discard(None)

    if hidden_ids:
        inherited_queryset = inherited_queryset.exclude(id__in=hidden_ids)

    queryset = direct_queryset | inherited_queryset
    queryset = queryset.distinct()

    if active_only:
        queryset = queryset.filter(active=True)

    return queryset


def get_manageable_numbers_qs(user, action='change'):
    if user is None or not user.is_authenticated:
        return PhoneNumber.objects.none()

    if user.is_superuser:
        return PhoneNumber.objects.all()

    return PhoneNumber.objects.filter(owner=user)


def get_manageable_groups_qs(user, action='change'):
    if user is None or not user.is_authenticated:
        return Group.objects.none()

    if user.is_superuser:
        return Group.objects.all()

    return Group.objects.filter(owner=user)


def get_accessible_rules_qs(user):
    if user is None or not user.is_authenticated:
        return AutomationRule.objects.none()

    if user.is_superuser:
        return AutomationRule.objects.all()

    return AutomationRule.objects.filter(Q(owner=user) | Q(users=user)).distinct()


def get_manageable_rules_qs(user, action='change'):
    if user is None or not user.is_authenticated:
        return AutomationRule.objects.none()

    if user.is_superuser:
        return AutomationRule.objects.all()

    return AutomationRule.objects.filter(owner=user)


def get_accessible_device_objects_qs(user):
    if user is None or not user.is_authenticated:
        return DeviceObject.objects.none()

    if user.is_superuser:
        return DeviceObject.objects.all()

    return DeviceObject.objects.filter(owner=user)


def get_manageable_device_objects_qs(user, action='change'):
    if user is None or not user.is_authenticated:
        return DeviceObject.objects.none()

    if user.is_superuser:
        return DeviceObject.objects.all()

    return DeviceObject.objects.filter(owner=user)
