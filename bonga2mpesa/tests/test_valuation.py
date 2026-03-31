import pytest
from app.services.valuation_service import ValuationService


@pytest.fixture
def svc():
    return ValuationService()


def test_compute_expected_payout(svc):
    # 767 bonga * 0.133 = 102.011 → 102.01
    result = svc.compute_expected_payout(767)
    assert result == pytest.approx(102.01, abs=0.01)


def test_compute_safaricom_inflow(svc):
    # 767 * 0.2 = 153.4
    result = svc.compute_safaricom_inflow(767)
    assert result == pytest.approx(153.4, abs=0.01)


def test_is_profitable_true(svc):
    assert svc.is_profitable(153.4, 102.0) is True


def test_is_profitable_false_when_payout_exceeds_inflow(svc):
    assert svc.is_profitable(100.0, 150.0) is False


def test_is_profitable_false_when_equal(svc):
    assert svc.is_profitable(100.0, 100.0) is False


def test_validate_safaricom_amount_valid(svc):
    # Exact match
    assert svc.validate_safaricom_amount(767, 153.4) is True


def test_validate_safaricom_amount_within_tolerance(svc):
    # Within 5%
    assert svc.validate_safaricom_amount(767, 150.0) is True


def test_validate_safaricom_amount_out_of_tolerance(svc):
    # More than 5% off
    assert svc.validate_safaricom_amount(767, 100.0) is False
