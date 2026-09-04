# Gym Owner Guide

> **Run the floor. Know your members. Act before the numbers become problems.**

This guide explains how to use Gym Console as a gym owner. Your workspace combines member management, payments, attendance, classes, inquiries, team access, billing, and AI Insights in one place.

---

## 1. Your Daily Workspace

After signing in, use the sidebar:

- **AI Insights**: attendance, revenue, churn, follow-ups, and practical recommendations.
- **Members**: add, search, update, and review member records.
- **Plans**: create the memberships your gym sells.
- **Payments**: record payments, email receipts, and download PDF receipts.
- **Classes**: create classes, assign trainers, and book members.
- **Attendance**: scan faces or mark members manually.
- **Inquiries**: manage prospects and follow-up history.
- **Staff**: invite team members and control privileges.
- **Notifications**: send renewal reminders and inactivity nudges.
- **Billing**: view your platform subscription and subscribe to a plan.
- **Activity history**: review staff and trainer actions.

Your available menu can differ for staff and trainers because the owner controls privileges.

---

## 2. Sign In and Secure Your Account

1. Open the application URL.
2. Enter your email and password.
3. Select **Sign in**.
4. Confirm that your gym name appears in the sidebar.
5. Log out when using a shared device.

Use a unique password. Never share it in email, chat, screenshots, or support tickets.

---

## 3. Start with Membership Plans

1. Open **Plans**.
2. Enter a plan name, such as `Monthly Strength`.
3. Enter the price.
4. Enter the duration in days.
5. Select **Add plan**.

Create plans before adding members if you want members and payments to be linked to a plan.

---

## 4. Add a Member

1. Open **Members**.
2. Enter the member's full name.
3. Add phone and email when available.
4. Type a plan name in the plan field.
5. Select the suggested plan.
6. Select **Add member**.

The plan lookup uses suggestions. Select a suggestion rather than typing an arbitrary value.

If an email is available, the member receives a welcome email after creation.

### Member detail page
Open a member's name to:

- Edit name, phone, email, status, or plan.
- Upload a profile photo.
- Review attendance.
- Review payment history.
- Review churn risk.
- Download payment receipts.

Statuses include **active**, **expired**, and **frozen**.

---

## 5. Upload a Member Photo

1. Open the member detail page.
2. Select the photo upload control.
3. Choose a clear face photo.
4. Submit the upload.

Photos are stored in Cloudflare R2 when configured and remain private behind authenticated routes. The same photo is used by the face attendance scanner.

Use a well-lit, front-facing photo with one person visible. If face recognition cannot identify the member, use manual attendance while replacing the photo with a clearer image.

---

## 6. Record Attendance

### Face scan

1. Open **Attendance**.
2. Select **Open camera**.
3. Allow browser camera access.
4. Ask the member to face the camera.
5. Wait for the check-in or check-out result.
6. Select **Stop camera** when finished.

The scanner toggles attendance: the first successful scan checks in, and a later scan checks out. Checkout is protected by a minimum 15-minute gap.

### Manual mark

1. Open **Attendance**.
2. Type the member's name in the member lookup.
3. Select the suggested member.
4. Select **Mark present**.

Use the **Today** and **Last 30 days** views to inspect records.

### Attendance insights

The AI Insights dashboard shows:

- Traffic by hour.
- Busiest hour.
- Quietest active hour.
- Average visit duration.
- Today's check-ins.
- Members currently in the gym.
- Attendance health.

Use the busiest-hour signal to schedule front-desk coverage and the quietest-hour signal for campaigns or trainer availability.

---

## 7. Record a Payment

1. Open **Payments**.
2. Type a member's name and select the suggestion.
3. Type a plan and select the suggestion, if applicable.
4. Enter the amount.
5. Choose a payment method:
   - Cash
   - UPI
   - Card
   - Bank transfer
6. If the method is UPI, enter the UTR or transaction ID.
7. Select **Log payment**.

UPI payments cannot be submitted without a transaction reference.

After a successful payment:

- The member becomes active.
- The selected plan is assigned.
- The next due date is calculated from plan duration.
- A confirmation email is sent if the member has an email address.
- The branded PDF receipt is attached to that email.

The payment table shows the method and transaction reference. Select **Download PDF** to download the receipt again.

---

## 8. Understand the Receipt Email

The payment email includes:

- Gym name
- Member name
- Amount paid
- Plan
- Payment date
- Payment method
- UTR or transaction ID when supplied
- Next renewal date
- PDF receipt attachment

If the email does not arrive, verify the member email and ask the platform administrator to check SMTP configuration.

---

## 9. Use AI Insights

The AI Insights dashboard is a decision surface, not a replacement for judgement.

### Read the key panels

- **Today's check-ins**: immediate daily traffic.
- **Currently in gym**: live open visits.
- **Active members**: members currently eligible.
- **Expired members**: renewal opportunities.
- **Follow-ups due**: prospects requiring action today.
- **Revenue this month**: current-month payment total.
- **Traffic by time**: demand by hour over the last 30 days.
- **At-risk members**: members with medium or high churn risk.
- **Plan adoption**: which plans members actually use.
- **Business signals**: attendance, average visits, renewal pipeline, and revenue per active member.
- **Growth opportunities**: lead conversion, frozen-member, and revenue actions.

### Turn insight into action

- Contact high-risk members personally.
- Schedule staff around peak hours.
- Contact members whose renewal is due within 30 days.
- Follow up with open inquiries.
- Offer a restart conversation to frozen members.
- Compare revenue per active member with your plan pricing.

### Download a report

1. Open **AI Insights**.
2. Select **Download report**.
3. Save the CSV file for review or sharing.

The report contains summary metrics and member status/plan details for your gym only.

---

## 10. Manage Inquiries

1. Open **Inquiries**.
2. Add the prospect's name, phone, email, source, interested plan, and follow-up date.
3. Open an inquiry to review details.
4. Add notes and outcomes after each conversation.
5. Set the next follow-up date.
6. Select **Send reminder email** when appropriate.
7. Convert successful prospects to members or mark them lost.

Every successful reminder appears in **Follow-up history** as an email event with its timestamp.

---

## 11. Invite Staff and Trainers

1. Open **Staff**.
2. Enter the team member's email.
3. Create a temporary password.
4. Choose **Staff** or **Trainer**.
5. Select **Send invite**.

The invitation email includes the login email, temporary password, role, and gym name. Ask the recipient to change the temporary password after signing in.

### Manage privileges

For each staff member or trainer, choose the areas they can access:

- Dashboard
- Members
- Attendance
- Payments
- Classes
- Inquiries
- Notifications

Select **Save privileges**. Disabled areas disappear from navigation and are also blocked at the server/API level.

### Suggested roles

**Front-desk staff**

- Dashboard
- Members
- Attendance
- Payments
- Classes
- Inquiries
- Notifications

**Trainer**

- Dashboard
- Attendance
- Classes

Grant payment, member, or inquiry access only when the job requires it.

---

## 12. Review Activity History

Open **Activity history** to review staff and trainer actions.

Entries can include:

- Member created
- Payment recorded
- Member checked in or out
- Class booked
- Inquiry created
- Reminder sent
- Follow-up added
- API mutation completed

Use this history for coaching, handover, support investigations, and accountability. It records the actor, action, details, and timestamp.

---

## 13. Create Classes and Book Members

### Create a class

1. Open **Classes**.
2. Enter the class name.
3. Choose the day.
4. Enter the start time as `HH:MM`.
5. Set duration and capacity.
6. Type a trainer email and choose the suggested trainer.
7. Select **Add class**.

### Book a member

1. Type the class name and select the suggested class.
2. Type the member name and select the suggested member.
3. Select **Book**.

Bookings are blocked when the class is full or the member is already booked.

---

## 14. Notifications

Open **Notifications** to send:

- Renewal reminders for members approaching their due date.
- Inactivity nudges for members with churn risk.

Review the result counts for sent, skipped, and failed messages. Members without email addresses are skipped.

---

## 15. Billing and Subscription

Open **Billing** to see:

- Current platform subscription status.
- Assigned platform plan.
- Trial end date.
- Current billing period end date.
- Available platform plans.

Only the gym owner can change the platform subscription. Depending on configuration, subscription checkout uses Razorpay or a local simulated subscription mode.

---

## 16. Weekly Owner Checklist

- Review AI Insights and at-risk members.
- Follow up with today's inquiries.
- Check renewals due within 30 days.
- Reconcile payment totals.
- Review expired and frozen members.
- Check activity history for unusual actions.
- Confirm staff privileges still match responsibilities.
- Review class capacity and trainer schedules.
- Confirm member photos are available for scanner users.

---

## 17. Troubleshooting

### A lookup does not submit
Choose an item from the suggestions. Typing a name without selecting a suggestion does not create a valid member, plan, class, or trainer ID.

### A UPI payment is rejected
Enter the UTR or transaction ID. It is required for UPI payments.

### A receipt email is missing
Check that the member has an email address. Ask the platform administrator to verify SMTP settings and sender verification.

### Face recognition is unavailable
Confirm the native `face-recognition` dependency is installed and the server has restarted. Use manual attendance while troubleshooting. Browser camera access also requires HTTPS in production.

### A team member cannot open a page
Review their privileges on the Staff page. The owner can enable the required area and save the changes.

### A member photo is missing
Check R2 configuration, bucket access, and authenticated access to the member route. Existing local photos remain supported if they have not been migrated.

---

## 18. Success Definition

Your gym is using the platform well when:

- Every member has accurate contact and plan information.
- Every payment has the correct method and reference.
- Receipts reach members automatically.
- Attendance shows real traffic patterns.
- Follow-ups are recorded after every prospect conversation.
- Staff privileges match actual responsibilities.
- Activity history explains team actions.
- AI Insights leads to concrete weekly decisions.
