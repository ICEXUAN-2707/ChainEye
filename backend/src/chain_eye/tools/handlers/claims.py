"""Claim reference validation handler."""
import re

from chain_eye.domain.contracts import Claim


def validate_claims(context,claims,allowed_evidence_ids,allowed_calculation_ids,allowed_assumption_ids):
    evidence=set(allowed_evidence_ids);calculations=set(allowed_calculation_ids);assumptions=set(allowed_assumption_ids)
    validated=[]
    for raw in claims:
        context.check_budget()
        claim=Claim.model_validate(raw)
        refs_valid=(
            set(claim.evidence_ids)<=evidence
            and set(claim.counter_evidence_ids)<=evidence
            and set(claim.calculation_ids)<=calculations
            and set(claim.assumption_ids)<=assumptions
        )
        numeric=bool(re.search(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?',claim.text))
        supported=bool(claim.evidence_ids or claim.calculation_ids)
        if not refs_valid:status='rejected'
        elif numeric and not supported:status='insufficient'
        elif claim.review_status=='rejected':status='rejected'
        elif supported:status='pending'
        else:status='insufficient'
        validated.append(claim.model_copy(update={'review_status':status}))
    return validated
