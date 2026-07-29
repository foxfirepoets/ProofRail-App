"""Offline tests for the Gmail disposition engine. No network. Proves directive §8 / §14 Inbox Tests.

Run:  python test/test_gmail_disposition.py     (exits non-zero on any failure)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from gmail_disposition import Facts, decide_disposition, Disposition  # noqa: E402


class InboxDispositionTests(unittest.TestCase):
    def test_classified_no_attachment_is_archived(self):
        d = decide_disposition(Facts("APPROVAL", audit_logged=True, attachment_filed=True))
        self.assertTrue(d.remove_inbox)
        self.assertIn("ProofRail/Processed", d.final_labels)
        self.assertFalse(d.trash)

    def test_attachment_not_archived_until_filed(self):
        d = decide_disposition(Facts("INVOICE", has_attachment=True, attachment_filed=False,
                                     audit_logged=True, invoiceproof_verdict="PASS"))
        self.assertFalse(d.remove_inbox)
        self.assertEqual(d.stays_in_inbox_reason, "attachment not saved+filed")

    def test_attachment_archived_after_filed_and_logged(self):
        d = decide_disposition(Facts("INVOICE", has_attachment=True, attachment_filed=True,
                                     audit_logged=True, invoiceproof_verdict="PASS"))
        self.assertTrue(d.remove_inbox)
        self.assertIn("ProofRail/Approval", d.final_labels)

    def test_fail_invoice_quarantined_out_of_inbox_after_exception(self):
        d = decide_disposition(Facts("INVOICE", has_attachment=True, attachment_filed=True,
                                     audit_logged=True, invoiceproof_verdict="FAIL",
                                     exception_recorded=True))
        self.assertIn("ProofRail/Quarantined", d.final_labels)
        self.assertTrue(d.remove_inbox)

    def test_fail_invoice_stays_until_exception_recorded(self):
        d = decide_disposition(Facts("INVOICE", has_attachment=True, attachment_filed=True,
                                     audit_logged=True, invoiceproof_verdict="FAIL",
                                     exception_recorded=False))
        self.assertFalse(d.remove_inbox)

    def test_bank_change_out_only_after_exception(self):
        held = decide_disposition(Facts("BANK_NOTICE", audit_logged=True, attachment_filed=True,
                                        exception_recorded=False))
        self.assertFalse(held.remove_inbox)
        done = decide_disposition(Facts("BANK_NOTICE", audit_logged=True, attachment_filed=True,
                                        exception_recorded=True))
        self.assertTrue(done.remove_inbox)
        self.assertIn("ProofRail/Risk-BankChange", done.final_labels)

    def test_low_value_marketing_trashed(self):
        d = decide_disposition(Facts("MARKETING", confidence=0.99, has_attachment=False,
                                     is_business_thread=False, has_pending_action=False,
                                     audit_logged=True))
        self.assertTrue(d.trash)
        self.assertTrue(d.remove_inbox)

    def test_marketing_with_attachment_archived_not_trashed(self):
        d = decide_disposition(Facts("MARKETING", confidence=0.99, has_attachment=True,
                                     attachment_filed=True, is_business_thread=False,
                                     audit_logged=True))
        self.assertFalse(d.trash)
        self.assertTrue(d.remove_inbox)  # archived instead

    def test_low_confidence_marketing_not_trashed(self):
        d = decide_disposition(Facts("MARKETING", confidence=0.5, has_attachment=False,
                                     is_business_thread=False, audit_logged=True))
        self.assertFalse(d.trash)

    def test_business_thread_never_trashed(self):
        d = decide_disposition(Facts("MARKETING", confidence=0.99, has_attachment=False,
                                     is_business_thread=True, audit_logged=True))
        self.assertFalse(d.trash)

    def test_pending_action_never_trashed(self):
        d = decide_disposition(Facts("SPAM", confidence=0.99, has_attachment=False,
                                     is_business_thread=False, has_pending_action=True,
                                     audit_logged=True))
        self.assertFalse(d.trash)

    def test_not_logged_stays_in_inbox(self):
        d = decide_disposition(Facts("APPROVAL", audit_logged=False, attachment_filed=True))
        self.assertFalse(d.remove_inbox)
        self.assertEqual(d.stays_in_inbox_reason, "no audit event yet")

    # ---- ProofRail/Action selectivity (LOCKED decision item 2 / migration_artifacts/
    # 13_Action_Selectivity_Change.md) -- Action must be a real low-confidence signal, never a
    # default just because a message landed in one of the three "ambiguous-capable" classes.
    def test_confident_draw_sheet_routes_processed_not_action(self):
        d = decide_disposition(Facts("DRAW_SHEET", confidence=0.95, audit_logged=True,
                                     attachment_filed=True))
        self.assertIn("ProofRail/Processed", d.final_labels)
        self.assertNotIn("ProofRail/Action", d.final_labels)

    def test_low_confidence_draw_sheet_still_flags_action(self):
        d = decide_disposition(Facts("DRAW_SHEET", confidence=0.5, audit_logged=True,
                                     attachment_filed=True))
        self.assertIn("ProofRail/Action", d.final_labels)

    def test_confident_vendor_inquiry_routes_processed_not_action(self):
        d = decide_disposition(Facts("VENDOR_INQUIRY", confidence=0.9, audit_logged=True,
                                     attachment_filed=True))
        self.assertIn("ProofRail/Processed", d.final_labels)
        self.assertNotIn("ProofRail/Action", d.final_labels)

    def test_confident_lender_correspondence_routes_processed_not_action(self):
        d = decide_disposition(Facts("LENDER_CORRESPONDENCE", confidence=0.9, audit_logged=True,
                                     attachment_filed=True))
        self.assertIn("ProofRail/Processed", d.final_labels)
        self.assertNotIn("ProofRail/Action", d.final_labels)

    def test_default_confidence_is_never_action(self):
        # Facts.confidence defaults to 1.0 -- callers that don't pass a real confidence signal
        # must NOT accidentally fall into the old blanket-Action behavior.
        d = decide_disposition(Facts("LENDER_CORRESPONDENCE", audit_logged=True, attachment_filed=True))
        self.assertNotIn("ProofRail/Action", d.final_labels)

    def test_permanent_delete_is_not_representable(self):
        # The engine's output type has no way to express permanent deletion.
        self.assertFalse(hasattr(Disposition(), "permanent_delete"))
        d = decide_disposition(Facts("SPAM", confidence=1.0, is_business_thread=False,
                                     audit_logged=True))
        self.assertNotIn("permanent_delete", vars(d))


if __name__ == "__main__":
    unittest.main(verbosity=2)
