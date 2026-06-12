from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import AutomationRule, OutgoingAction


class Command(BaseCommand):
    help = (
        'Převede historické klony AutomationRule (vytvořené pro více ownerů) '
        'na sdílené pravidlo přes pole users.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Provede změny. Bez tohoto přepínače běží jen dry-run.',
        )

    @staticmethod
    def _rule_fingerprint(rule):
        return (
            rule.name,
            rule.description,
            rule.active,
            rule.priority,
            rule.event_type,
            rule.match_type,
            rule.source_number,
            rule.source_group_id,
            tuple(sorted(rule.source_groups.values_list('id', flat=True))),
            rule.action,
            tuple(sorted(rule.target_numbers.values_list('id', flat=True))),
            tuple(sorted(rule.target_groups.values_list('id', flat=True))),
            rule.use_message_flag,
            rule.message_flag,
            rule.forward_to_number,
            rule.include_original_message,
            rule.custom_message,
            rule.stop_processing,
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        rules = list(
            AutomationRule.objects.all()
            .prefetch_related('source_groups', 'target_numbers', 'target_groups', 'users')
            .order_by('id')
        )

        grouped = defaultdict(list)
        for rule in rules:
            grouped[self._rule_fingerprint(rule)].append(rule)

        candidate_groups = [group for group in grouped.values() if len(group) > 1]

        if not candidate_groups:
            self.stdout.write(self.style.SUCCESS('Nenalezeny žádné kandidátní klony pravidel.'))
            return

        merged_groups = 0
        deleted_rules = 0
        reassigned_actions = 0

        @transaction.atomic
        def _apply_group(canonical_rule, duplicate_rules):
            nonlocal deleted_rules, reassigned_actions

            merged_user_ids = set(canonical_rule.users.values_list('id', flat=True))

            for duplicate_rule in duplicate_rules:
                if duplicate_rule.owner_id != canonical_rule.owner_id:
                    merged_user_ids.add(duplicate_rule.owner_id)

                duplicate_user_ids = set(duplicate_rule.users.values_list('id', flat=True))
                merged_user_ids.update(duplicate_user_ids)

                updated = OutgoingAction.objects.filter(rule=duplicate_rule).update(rule=canonical_rule)
                reassigned_actions += updated

                duplicate_rule.delete()
                deleted_rules += 1

            merged_user_ids.discard(canonical_rule.owner_id)
            canonical_rule.users.set(sorted(merged_user_ids))

        for group in candidate_groups:
            canonical_rule = group[0]
            duplicate_rules = group[1:]

            owner_ids = sorted({rule.owner_id for rule in group})
            if len(owner_ids) < 2:
                continue

            merged_groups += 1
            self.stdout.write(
                f'Kandidát #{merged_groups}: canonical rule id={canonical_rule.id}, '
                f'owner={canonical_rule.owner_id}, duplicity={len(duplicate_rules)}'
            )

            if apply_changes:
                _apply_group(canonical_rule, duplicate_rules)

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    f'Dry-run dokončen. Kandidátních skupin: {merged_groups}. '
                    'Pro provedení spusťte s --apply.'
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Migrace dokončena. Sloučené skupiny: {merged_groups}, '
                f'smazané klony: {deleted_rules}, přesměrované akce: {reassigned_actions}.'
            )
        )
