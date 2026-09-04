# Nexus Platform Owner Guide

> **Control the platform. Grow the network. Keep every gym accountable.**

This handbook is for the person who owns and operates the Gym SaaS platform. The super-admin manages the commercial layer: platform plans, gym onboarding, subscriptions, owner accounts, operational settings, and platform-wide health.

---

## 1. Your Role

The super-admin is above any individual gym. You can:

- Create and manage gyms.
- Create, edit, and retire platform subscription plans.
- Assign a platform plan to every gym.
- Set subscription states: trial, active, cancelled, or past due.
- Manage gym owner email addresses and passwords.
- Review platform-wide member, attendance, revenue, and subscription metrics.
- Configure follow-up reminder timing.
- Test SMTP email delivery.
- Review whether platform plans are being adopted.

The super-admin does **not** use the normal gym dashboard. Gym owners manage their own members, payments, classes, attendance, and staff after they receive access.

---

## 2. Sign In

1. Open the application URL.
2. Enter the super-admin email and password.
3. Submit the form.
4. You will be redirected to `/app/superadmin`.
5. Use **Log out** when finished, especially on shared computers.

### Security rule
Never share credentials in chat, documentation, screenshots, source code, or `.env` files committed to Git. Store secrets in the deployment platform's secret manager or an ignored local `.env` file.

---

## 3. Super-Admin Navigation

| Area | Purpose |
|---|---|
| **Overview** | Fast platform snapshot and common actions |
| **Analytics** | Platform health, subscription mix, payment totals, and plan adoption |
| **Gyms** | Review, create, edit, and remove gyms |
| **Plans** | Create, edit, and manage platform subscription plans |
| **Settings** | SMTP test and reminder scheduler configuration |

The active tab is highlighted in the left navigation.

---

## 4. Recommended First-Time Setup

### Step 1: Create platform plans
Open **Plans** and create the packages you want to sell.

For each plan define:

- Plan name
- Price in rupees
- Billing interval: monthly, quarterly, or yearly
- Optional member limit
- Optional Razorpay plan ID

Use meaningful names such as `Starter`, `Growth`, and `Pro`.

### Step 2: Configure email
Open **Settings** and verify that SMTP is configured. Send a test email to an address you control.

Email is used for:

- SMTP verification
- Staff and trainer invitations
- Payment confirmations
- Payment receipt attachments
- Inquiry follow-up reminders
- Member welcome messages

### Step 3: Create a gym
Open **Gyms** and complete:

1. Gym name
2. Owner email
3. Owner password
4. Platform plan
5. Subscription state

A platform plan is required. A gym should never be onboarded without a commercial plan attached.

### Step 4: Confirm access
Ask the gym owner to sign in and verify:

- Dashboard loads
- Billing shows the assigned platform plan
- Members can be added
- Payment receipt can be downloaded
- Staff invitations can be sent

---

## 5. Gym Lifecycle Management

### Create a gym
Use **Add gym** or the create form in the Gyms area. Select a platform plan before submitting.

### Edit a gym
1. Open **Gyms**.
2. Select **Open** beside the gym.
3. Edit the gym name, owner email, owner password, platform plan, or subscription state.
4. Select **Save gym**.

The owner password is optional during edits. Leave it blank to keep the current password.

### Subscription states

- **Trial**: onboarding or evaluation period.
- **Active**: paying and operational.
- **Cancelled**: subscription ended.
- **Past due**: payment attention required.

Use the state that reflects the commercial reality. The dashboard uses these states for platform health reporting.

### Delete a gym
Delete only when the business relationship and retention requirements allow it. Gym deletion removes the gym's related users, members, plans, payments, attendance, classes, and bookings.

This action is destructive and should be treated as permanent.

---

## 6. Platform Plan Management

### Create a plan
Use the quick form on Overview or the full form in Plans. The full form supports billing interval, member limit, and Razorpay mapping.

### Edit a plan
1. Open **Plans**.
2. Select **Edit**.
3. Update the package details.
4. Select **Save plan**.

### Delete a plan safely
A plan cannot be deleted while gyms are assigned to it. First move those gyms to another plan, then delete the unused plan.

This prevents active gym subscriptions from losing their commercial reference.

---

## 7. Read the Platform Analytics

Open **Analytics** to review:

- Total gyms
- Total platform users
- Total members
- Active, expired, and frozen members
- Attendance records
- Today's attendance
- Current-month payments
- All-time payment volume
- Approximate recurring revenue from active gym subscriptions
- Subscription mix by status
- Plan adoption by gyms and members

### How to use the signals

- A high **trial** count means onboarding or conversion work is needed.
- **Past due** gyms need billing follow-up.
- Low plan adoption may indicate pricing, packaging, or onboarding friction.
- Rising member counts without active subscriptions may require commercial review.
- High attendance with weak subscription conversion can indicate healthy product use but weak billing operations.

Numbers are operational signals, not financial accounting. Reconcile revenue with your payment provider and accounting system.

---

## 8. Email and Reminder Settings

### SMTP test
1. Open **Settings**.
2. Confirm the configured sender.
3. Enter a recipient, subject, and message.
4. Select **Send test email**.
5. Check inbox and spam folders.

### Reminder schedule
Set the platform default reminder time in `HH:MM` UTC format, for example `08:00`.

The scheduler sends reminders for inquiries whose next follow-up is tomorrow. You can also select **Send due reminders now** for a manual run.

Successful automatic reminders are recorded in the gym's follow-up history.

---

## 9. Data, Photos, and R2

Member photos are stored in Cloudflare R2 when the R2 settings are configured. Objects use a gym-scoped path such as:

```text
member-photos/<gym-id>/<member-id>.<extension>
```

Photos are served through authenticated application routes. Do not make member photos public unless your privacy policy explicitly allows it.

Existing local photos can be migrated with:

```bash
source env/bin/activate
python -m scripts.migrate_photos_to_r2
```

Required environment variables include `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, and `R2_ENDPOINT_URL`.

Rotate credentials immediately if they are exposed.

---

## 10. Operational Checklist

### Daily

- Review Overview and Analytics.
- Check trial and past-due gyms.
- Check SMTP status if owners report missing emails.
- Review recent gym onboarding.

### Weekly

- Review plan adoption.
- Review active versus trial gyms.
- Confirm platform revenue against the payment provider.
- Review owner activity when investigating support issues.
- Check R2 storage and backup policy.

### Before deleting anything

- Confirm the gym or plan is no longer needed.
- Export required business records.
- Confirm there are no active subscriptions or assigned gyms.
- Confirm the action with the business owner.

---

## 11. Troubleshooting

### A gym cannot be created
Confirm that a platform plan is selected and that the owner email is not already registered.

### A plan cannot be deleted
At least one gym still uses it. Edit those gyms and assign another plan first.

### An email was not received
Check SMTP host, port, username, password, sender verification, spam folders, and provider logs.

### A photo is missing
Confirm R2 credentials, bucket name, endpoint, object permissions, and the member's authenticated access. Existing local files are still supported when the database path points to a local file.

### A dashboard is empty
The dashboard is data-driven. Add members, attendance, payments, inquiries, and classes before expecting meaningful analytics.

---

## 12. Success Definition

The platform is healthy when:

- Every gym has a valid platform plan.
- Subscription states match commercial reality.
- Owners can sign in and complete daily operations.
- Payment emails and receipt attachments arrive.
- Follow-up reminders are visible in history.
- Activity history explains staff and trainer actions.
- Member photos are stored privately and retrievable.
- Analytics support decisions instead of showing placeholder values.
