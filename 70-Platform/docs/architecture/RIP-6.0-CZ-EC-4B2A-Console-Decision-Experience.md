# CZ-EC-4B2A — Console Decision Experience

The console reopens a retained onboarding run and presents persisted immutable
classification requests with the deterministic retained-manifest scope preview.
It collects reviewer identity, role, authority claim, selected treatment, and a
rationale, then asks for explicit confirmation.

After confirmation, the console invokes only the promoted `accept_decision`
service and `integrate_persisted_classifications` service. The returned
readiness state and its blocking conditions are displayed to the reviewer.
The console does not reconstruct policy, calculate readiness, verify customer
sources, resume onboarding, or write lifecycle state.

Customer repositories remain read-only. The only writes are the immutable
governed records and summaries already owned by the promoted service layer.

CZ-EC-4B2B remains responsible for any actual onboarding-resume execution,
fresh source verification, lifecycle advancement, and notifications.
