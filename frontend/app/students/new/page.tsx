'use client';

/**
 * New Student, step 1 of 5 — the admissions desk's own form, laid out as the
 * desk already knows it: Picture, Roll No., Name, Gender, Date of Birth,
 * Address, Nationality, Mobile, Landline, School/College, Email, Owner.
 *
 * Why this exists beside `/admissions/new`: that wizard asks the same
 * questions in the order an engineer would group them. This one asks them in
 * the order the counsellor already asks them, with the labels they already
 * say out loud, because the people using it have typed this form several
 * thousand times and the muscle memory is worth more than our grouping.
 *
 * Three fields repeat — Mobile, Landline, Email. The *first* of each is the
 * student's account (`phone`, `email`); the rest are contacts
 * (`students.StudentContact`), which never sign anybody in. The tick beside
 * a row makes it the primary one, which is why it is a radio in behaviour
 * even though the original draws a checkbox: two primaries is not a state
 * that means anything.
 *
 * Saving creates the student and moves to step 2. There is no draft: a
 * half-made student with no account is worse than a form somebody has to
 * finish, and the duplicate check the server runs on save is the thing that
 * stops the same person being registered twice.
 */

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Trash2 } from 'lucide-react';

import { AddAnother, FormRow } from '@/components/classpro/form-row';
import { StepBar, type WizardStep } from '@/components/classpro/step-bar';
import { Tips } from '@/components/classpro/tips';
import { CollegePicker } from '@/components/admissions/college-picker';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input, Select, Textarea } from '@/components/ui/input';
import { useApi } from '@/hooks/use-api';
import { fieldErrors, unshownError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { createStudent } from '@/lib/people';
import type { College } from '@/lib/people';
import type { PublicSettings } from '@/lib/settings';
import type { Paginated, User } from '@/types/api';

export const WIZARD_STEPS: WizardStep[] = [
  { key: 'student', label: 'Student Details' },
  { key: 'guardian', label: 'Guardian Details' },
  { key: 'admission', label: 'Admission Details' },
  { key: 'payment', label: 'Payment Details' },
  { key: 'batch', label: 'Batch Details' },
];

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/** 1900 to this year, newest first — a student is far likelier to be 20 than 90. */
function years(): number[] {
  const now = new Date().getFullYear();
  return Array.from({ length: now - 1900 + 1 }, (_, index) => now - index);
}

/** The dialling codes the desk actually meets. India first and selected. */
const COUNTRY_CODES = ['+91', '+1', '+44', '+61', '+971', '+977'];

const NATIONALITIES = ['India', 'Nepal', 'Bangladesh', 'Sri Lanka', 'Bhutan', 'Other'];

interface Repeatable {
  /** A key React can hold on to while rows are added and removed — never the
   *  array index, which changes under the row when an earlier one goes. */
  key: string;
  code: string;
  value: string;
}

let rowCounter = 0;
function blankRow(code = ''): Repeatable {
  rowCounter += 1;
  return { key: `row-${rowCounter}`, code, value: '' };
}

export function NewStudentForm() {
  const router = useRouter();
  const settings = useApi<PublicSettings>('/api/v1/settings/public/');
  // Who can own a student: the staff this caller may list. A counsellor with
  // no right to read the user list simply gets themselves, which the server
  // defaults to anyway.
  const staff = useApi<Paginated<User>>('/api/v1/users/?page_size=100');

  const [rollNumber, setRollNumber] = useState('');
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [gender, setGender] = useState('male');
  const [day, setDay] = useState('');
  const [month, setMonth] = useState('');
  const [year, setYear] = useState('');
  const [address, setAddress] = useState('');
  const [area, setArea] = useState('');
  const [landmark, setLandmark] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [pincode, setPincode] = useState('');
  const [nationality, setNationality] = useState('India');
  const [mobiles, setMobiles] = useState<Repeatable[]>([blankRow('+91')]);
  const [primaryMobile, setPrimaryMobile] = useState(0);
  const [landlines, setLandlines] = useState<Repeatable[]>([blankRow()]);
  const [college, setCollege] = useState<College | null>(null);
  const [emails, setEmails] = useState<Repeatable[]>([blankRow()]);
  const [primaryEmail, setPrimaryEmail] = useState(0);
  const [owner, setOwner] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const branchName = settings.data?.institution_name ?? '';

  function updateRow(
    rows: Repeatable[],
    setRows: (rows: Repeatable[]) => void,
    index: number,
    patch: Partial<Repeatable>,
  ) {
    setRows(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  }

  function removeRow(
    rows: Repeatable[],
    setRows: (rows: Repeatable[]) => void,
    index: number,
    primary: number,
    setPrimary?: (value: number) => void,
  ) {
    // Never fewer than one row: an empty repeatable field has no "add
    // another" to click back from.
    const next = rows.length === 1 ? [blankRow(rows[0]?.code ?? '')] : rows.filter((_, i) => i !== index);
    setRows(next);
    if (setPrimary && primary >= next.length) setPrimary(0);
    else if (setPrimary && index < primary) setPrimary(primary - 1);
  }

  function dateOfBirth(): string | null {
    if (!day || !month || !year) return null;
    const monthNumber = String(MONTHS.indexOf(month) + 1).padStart(2, '0');
    return `${year}-${monthNumber}-${day.padStart(2, '0')}`;
  }

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (!firstName.trim()) found.first_name = 'Enter the first name.';
    if (!gender) found.gender = 'Choose one.';
    const email = emails[primaryEmail]?.value.trim() ?? '';
    if (!email) found.email = 'An email is needed — it is how they sign in.';
    if ((day || month || year) && !dateOfBirth()) {
      found.date_of_birth = 'Give the whole date, or leave all three blank.';
    }
    return found;
  }

  async function save() {
    const found = validate();
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setSaving(true);
    setErrors({});

    const primaryMobileRow = mobiles[primaryMobile];
    const extras = [
      ...mobiles
        .filter((_, index) => index !== primaryMobile)
        .map((row) => ({ kind: 'mobile' as const, code: row.code, value: row.value.trim() })),
      ...landlines.map((row) => ({
        kind: 'landline' as const,
        code: row.code.trim(),
        value: row.value.trim(),
      })),
      ...emails
        .filter((_, index) => index !== primaryEmail)
        .map((row) => ({ kind: 'email' as const, value: row.value.trim() })),
    ].filter((row) => row.value);

    try {
      const student = await createStudent({
        email: (emails[primaryEmail]?.value ?? '').trim(),
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        phone: primaryMobileRow?.value.trim()
          ? `${primaryMobileRow.code}${primaryMobileRow.value.trim().replace(/^\+?\d{1,3}(?=\d{10}$)/, '')}`
          : '',
        contacts: extras,
        profile: {
          roll_number: rollNumber.trim(),
          gender,
          date_of_birth: dateOfBirth(),
          address_line1: address.trim(),
          area: area.trim(),
          landmark: landmark.trim(),
          city: city.trim(),
          state: state.trim(),
          postal_code: pincode.trim(),
          nationality,
          college: college?.id ?? null,
          institution: college?.name ?? '',
          ...(owner ? { owner } : {}),
        },
      });
      router.push(`/students/${student.id}/guardians?new=1`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const stray = unshownError(errors, [
    'first_name',
    'middle_name',
    'last_name',
    'gender',
    'email',
    'phone',
    'date_of_birth',
    'roll_number',
  ]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-normal tracking-tight">
        New Student{branchName ? <span className="text-ink-muted"> ({branchName})</span> : null}
      </h1>

      <div className="overflow-hidden rounded-card border border-line bg-surface">
        <StepBar steps={WIZARD_STEPS} current="student" furthest="student" onSelect={() => {}} />

        <div className="grid gap-8 p-5 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <form
            className="min-w-0 divide-y divide-line/60"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            {stray ? <Alert variant="error">{stray}</Alert> : null}

            <FormRow label="Picture">
              <Button type="button" variant="outline" size="sm" disabled>
                Upload Image
              </Button>
              <p className="text-xs text-ink-muted">
                A picture can be added from the student&apos;s own record once they are saved.
              </p>
            </FormRow>

            <FormRow label="Roll No." htmlFor="roll-no" error={errors.roll_number}>
              <Input
                id="roll-no"
                value={rollNumber}
                onChange={(event) => setRollNumber(event.target.value)}
                placeholder="Enter roll number"
                className="max-w-xs"
              />
            </FormRow>

            <FormRow label="Name" required error={errors.first_name ?? errors.last_name}>
              <div className="grid gap-2 sm:grid-cols-3">
                <Input
                  aria-label="Firstname"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  placeholder="Firstname"
                />
                <Input
                  aria-label="Middlename"
                  value={middleName}
                  onChange={(event) => setMiddleName(event.target.value)}
                  placeholder="Middlename"
                />
                <Input
                  aria-label="Lastname"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  placeholder="Lastname"
                />
              </div>
            </FormRow>

            <FormRow label="Gender" required error={errors.gender}>
              <fieldset className="flex gap-5">
                <legend className="sr-only">Gender</legend>
                {[
                  { value: 'male', label: 'Male' },
                  { value: 'female', label: 'Female' },
                ].map((option) => (
                  <label key={option.value} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="radio"
                      name="gender"
                      value={option.value}
                      checked={gender === option.value}
                      onChange={() => setGender(option.value)}
                      className="size-4 accent-[var(--color-action)]"
                    />
                    {option.label}
                  </label>
                ))}
              </fieldset>
            </FormRow>

            <FormRow label="Date of Birth" error={errors.date_of_birth}>
              <div className="grid gap-2 sm:grid-cols-3">
                <Select aria-label="Day" value={day} onChange={(e) => setDay(e.target.value)}>
                  <option value="">Day</option>
                  {Array.from({ length: 31 }, (_, index) => index + 1).map((value) => (
                    <option key={value} value={String(value)}>
                      {value}
                    </option>
                  ))}
                </Select>
                <Select aria-label="Month" value={month} onChange={(e) => setMonth(e.target.value)}>
                  <option value="">Month</option>
                  {MONTHS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
                <Select aria-label="Year" value={year} onChange={(e) => setYear(e.target.value)}>
                  <option value="">Year</option>
                  {years().map((value) => (
                    <option key={value} value={String(value)}>
                      {value}
                    </option>
                  ))}
                </Select>
              </div>
            </FormRow>

            <FormRow label="Address">
              <div className="space-y-2">
                <Textarea
                  aria-label="Address"
                  rows={2}
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  placeholder="Address"
                />
                <Input
                  aria-label="Area"
                  value={area}
                  onChange={(event) => setArea(event.target.value)}
                  placeholder="Area"
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input
                    aria-label="Landmark"
                    value={landmark}
                    onChange={(event) => setLandmark(event.target.value)}
                    placeholder="landmark"
                  />
                  <Input
                    aria-label="City"
                    value={city}
                    onChange={(event) => setCity(event.target.value)}
                    placeholder="city"
                  />
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input
                    aria-label="State"
                    value={state}
                    onChange={(event) => setState(event.target.value)}
                    placeholder="state"
                  />
                  <Input
                    aria-label="Pincode"
                    value={pincode}
                    onChange={(event) => setPincode(event.target.value)}
                    placeholder="pincode"
                  />
                </div>
              </div>
            </FormRow>

            <FormRow label="Nationality" htmlFor="nationality">
              <Select
                id="nationality"
                value={nationality}
                onChange={(event) => setNationality(event.target.value)}
                className="max-w-xs"
              >
                {NATIONALITIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </FormRow>

            <FormRow label="Mobile" error={errors.phone}>
              <div className="space-y-2">
                {mobiles.map((row, index) => (
                  <div key={row.key} className="flex items-center gap-2">
                    <Select
                      aria-label={`Country code ${index + 1}`}
                      value={row.code}
                      onChange={(event) =>
                        updateRow(mobiles, setMobiles, index, { code: event.target.value })
                      }
                      className="w-24 shrink-0"
                    >
                      {COUNTRY_CODES.map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label={`Mobile number ${index + 1}`}
                      value={row.value}
                      onChange={(event) =>
                        updateRow(mobiles, setMobiles, index, { value: event.target.value })
                      }
                    />
                    <label className="flex shrink-0 items-center gap-1.5 text-xs text-ink-muted">
                      <input
                        type="radio"
                        name="primary-mobile"
                        checked={primaryMobile === index}
                        onChange={() => setPrimaryMobile(index)}
                        className="size-4 accent-[var(--color-action)]"
                      />
                      <span className="sr-only sm:not-sr-only">Primary</span>
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove mobile number ${index + 1}`}
                      onClick={() =>
                        removeRow(mobiles, setMobiles, index, primaryMobile, setPrimaryMobile)
                      }
                    >
                      <Trash2 className="size-4 text-action" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <AddAnother onClick={() => setMobiles([...mobiles, blankRow('+91')])}>
                  Add another mobile number
                </AddAnother>
              </div>
            </FormRow>

            <FormRow label="Landline">
              <div className="space-y-2">
                {landlines.map((row, index) => (
                  <div key={row.key} className="flex items-center gap-2">
                    <Input
                      aria-label={`STD code ${index + 1}`}
                      value={row.code}
                      onChange={(event) =>
                        updateRow(landlines, setLandlines, index, { code: event.target.value })
                      }
                      className="w-24 shrink-0"
                    />
                    <Input
                      aria-label={`Landline number ${index + 1}`}
                      value={row.value}
                      onChange={(event) =>
                        updateRow(landlines, setLandlines, index, { value: event.target.value })
                      }
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove landline number ${index + 1}`}
                      onClick={() => removeRow(landlines, setLandlines, index, 0)}
                    >
                      <Trash2 className="size-4 text-action" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <AddAnother onClick={() => setLandlines([...landlines, blankRow()])}>
                  Add another landline number
                </AddAnother>
              </div>
            </FormRow>

            <FormRow label="School/College" htmlFor="school">
              <div className="max-w-md">
                <CollegePicker id="school" value={college} onChange={setCollege} defaultCity={city} />
              </div>
            </FormRow>

            <FormRow label="Email" error={errors.email}>
              <div className="space-y-2">
                {emails.map((row, index) => (
                  <div key={row.key} className="flex items-center gap-2">
                    <Input
                      aria-label={`Email ${index + 1}`}
                      type="email"
                      value={row.value}
                      onChange={(event) =>
                        updateRow(emails, setEmails, index, { value: event.target.value })
                      }
                    />
                    <label className="flex shrink-0 items-center gap-1.5 text-xs text-ink-muted">
                      <input
                        type="radio"
                        name="primary-email"
                        checked={primaryEmail === index}
                        onChange={() => setPrimaryEmail(index)}
                        className="size-4 accent-[var(--color-action)]"
                      />
                      <span className="sr-only sm:not-sr-only">Primary</span>
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove email ${index + 1}`}
                      onClick={() => removeRow(emails, setEmails, index, primaryEmail, setPrimaryEmail)}
                    >
                      <Trash2 className="size-4 text-action" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <AddAnother onClick={() => setEmails([...emails, blankRow()])}>
                  Add another email
                </AddAnother>
                <p className="text-xs text-ink-muted">
                  The one marked primary is the address they sign in with. The rest are contacts.
                </p>
              </div>
            </FormRow>

            <FormRow label="Owner" htmlFor="owner">
              <Select
                id="owner"
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
                className="max-w-sm"
              >
                <option value="">Not assigned</option>
                {(staff.data?.results ?? []).map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name || person.email}
                  </option>
                ))}
              </Select>
            </FormRow>

            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={saving} className="bg-success hover:bg-success/90">
                {saving ? 'Saving…' : 'Save'}
              </Button>
              <Button type="button" variant="outline" onClick={() => router.push('/admin/students')}>
                Cancel
              </Button>
            </div>
          </form>

          <Tips>
            <p>
              Be sure to add mobile number of <strong className="text-ink">student</strong> in order
              to send payment reminder, exam result updates via sms.
            </p>
            <p>
              Also, add email for <strong className="text-ink">student</strong> to send exam results
              via email.
            </p>
          </Tips>
        </div>
      </div>
    </div>
  );
}

export default function NewStudentPage() {
  return (
    <RequireAuth capability={Capability.studentCreate}>
      <NewStudentForm />
    </RequireAuth>
  );
}
