# Synthetic Pass Case: Paragraph-End Citation Supports Multiple Sentences

This fixture is invented for regression testing. It does not contain private
application text.

## Expected Audit Results

- Do not flag every sentence as missing a citation.
- Treat the paragraph as citation-supported when the paragraph-end citation
  plausibly supports the related prior-work claims.
- Optionally flag uncertainty only when it is unclear whether the citation
  supports all major claims.

## Proposal Text

Distributed acoustic sensing has been used to measure vibration patterns over
long infrastructure spans. Prior work has shown that changes in modal frequency
and damping can indicate structural degradation before visible damage appears.
These measurements can support maintenance decisions when paired with calibrated
models [1].

Reference:

[1] Synthetic Reference, Journal of Invented Infrastructure Monitoring, 2024.
