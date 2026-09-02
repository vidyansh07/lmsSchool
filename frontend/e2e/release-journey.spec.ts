import { expect, test, type Page } from '@playwright/test';

import { DEMO_PASSWORD, signIn, signOut } from './helpers';

/**
 * §15.2 — the one journey the release depends on.
 *
 * An administrator builds a course, a module and a lesson; makes a batch, gives
 * it a timetable and turns that into classes; assigns a trainer and reassigns
 * one; adds a student and enrols them. A student learns, is marked present,
 * hands in work, is graded, sits a weekly test whose results are imported,
 * delivers a project, sits an examination, is found to have completed the
 * course, and is issued a certificate that an employer can verify from a
 * signed-out browser.
 *
 * Written as one test on purpose. These steps are not independent — each is the
 * precondition for the next — and splitting them would either repeat the setup
 * twenty times or couple them silently through execution order.
 *
 * Two deliberate notes on how it signs in as a student:
 *
 *   * Creating a student and *enrolling* them is done for real, on a brand-new
 *     account, because those are the steps under test.
 *   * The learning half then runs as a **seeded** student, also enrolled on the
 *     new batch by the same administrator. A newly created account has no
 *     usable password by design: §1 has the administrator send a set-password
 *     link rather than choose somebody's password for them, so there is no
 *     honest way for a browser test to sign in as one. Weakening that to make
 *     the test simpler would be trading a real security property for a
 *     convenience.
 *
 * Everything it creates carries a run stamp and is archived at the end, so it
 * can run against the same environment repeatedly. That is not tidiness: an
 * earlier run's leftovers are precisely what once stopped a journey finding the
 * thing it had just created.
 */
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const ADMIN = 'admin@demo.grras.invalid';
// Deliberately not trainer1 or student1/student2: every other spec uses those,
// and this journey changes their world — it takes a register on the trainer's
// day, hands work in as the student, and finishes their course. Run in the same
// suite, that leaves the other specs looking at a register already marked and a
// student already complete. A journey this long needs people of its own.
const TRAINER = 'trainer3@demo.grras.invalid';
const STUDENT = 'student7@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; the release journey needs seeded data.');

test.describe.configure({ mode: 'serial' });

async function selectContaining(page: Page, label: string, text: string) {
  const select = page.getByLabel(label);
  const option = select.locator('option', { hasText: text }).first();
  // Waited for explicitly, and reported with what the select actually held.
  // Without this a missing option is a bare timeout on `getAttribute`, which
  // says nothing about which select or what was in it.
  try {
    await option.waitFor({ state: 'attached', timeout: 20_000 });
  } catch {
    const available = await select.locator('option').allTextContents();
    throw new Error(
      `No "${label}" option matching ${JSON.stringify(text)}. Options: ${JSON.stringify(available)}`,
    );
  }
  const value = await option.getAttribute('value');
  expect(value, `the "${label}" option matching ${text} has no value`).toBeTruthy();
  await select.selectOption(value as string);
}

function localDateTime(offsetMinutes: number): string {
  const at = new Date(Date.now() + offsetMinutes * 60_000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

test('the release journey: set a course up, teach it, finish it, verify the certificate', async ({
  page,
}) => {
  test.setTimeout(900_000);

  const stamp = Date.now();
  const courseTitle = `Release Course ${stamp}`;
  const batchName = `Release Batch ${stamp}`;
  const newStudentEmail = `release-${stamp}@demo.grras.invalid`;
  const assignmentTitle = `Release exercise ${stamp}`;
  const testTitle = `Release weekly test ${stamp}`;
  const projectTitle = `Release project ${stamp}`;
  const examTitle = `Release examination ${stamp}`;

  // ========================================================================
  // 1. Administrator signs in
  // ========================================================================
  await signIn(page, ADMIN);

  // Clear anything a previous run left behind. A run that fails part-way never
  // reaches its teardown, and the batch it created keeps its timetable slot
  // reserved against the trainer — so the *next* run cannot book the same hour
  // and fails for a reason that has nothing to do with what it was testing.
  // Cancelling releases the slot, which is what the conflict rule says a
  // cancelled batch does.
  await page.request.get(`${API}/api/v1/auth/csrf/`);
  const csrf =
    (await page.context().cookies()).find((cookie) => cookie.name === 'grras_csrftoken')?.value ??
    '';
  const stale = await page.request.get(`${API}/api/v1/batches/?search=Release Batch&page_size=100`);
  if (stale.ok()) {
    const rows = (await stale.json()).results as { id: string; status: string }[];
    for (const row of rows.filter((batch) => batch.status !== 'cancelled')) {
      const cancelled = await page.request.post(`${API}/api/v1/batches/${row.id}/status/`, {
        data: { status: 'cancelled' },
        // Django checks the token *and* the origin of the request, so both go on
        // every write — a browser sends the second for free and this client
        // does not.
        headers: { 'X-CSRFToken': csrf, Referer: `${API}/` },
        failOnStatusCode: false,
      });
      expect(cancelled.ok(), `could not clear the stale batch: ${await cancelled.text()}`).toBeTruthy();
    }
  }

  // ========================================================================
  // 2–4. Course, module, lesson — and all three published
  // ========================================================================
  await page.goto('/admin/courses');
  await page.getByRole('button', { name: 'New course' }).click();
  await page.getByLabel('Title').fill(courseTitle);
  await page.getByLabel('Short description').fill('Built by the release journey.');
  await page.getByRole('button', { name: 'Create course' }).click();

  // Creating opens the editor, so there is no list to click back through.
  await expect(page.getByRole('heading', { name: courseTitle })).toBeVisible();
  const courseUrl = page.url();

  await page.getByLabel('New module title').fill('Module one');
  await page.getByRole('button', { name: 'Add module' }).click();
  await expect(page.getByText('Module one')).toBeVisible();

  await page.getByRole('button', { name: 'Add lesson' }).first().click();
  await page.getByLabel('Lesson title').fill('Lesson one');
  await page.getByLabel('Lesson body').fill('The first thing to read on this course.');
  await page.getByRole('button', { name: 'Create lesson' }).click();
  await expect(page.getByText('Lesson one')).toBeVisible();

  // A draft lesson inside a published module must not reach a student, so all
  // three levels are published explicitly, innermost first. Each control is
  // scoped to its own card: "Publish" appears three times on this screen and
  // means something different each time.
  const lessonRow = page.getByRole('listitem').filter({ hasText: 'Lesson one' }).first();
  await lessonRow.getByRole('button', { name: 'Edit' }).click();
  // Scoped to the lesson's own row: the module's Publish button sits above it
  // in the DOM, so an unscoped `.first()` publishes the wrong thing and leaves
  // the lesson a draft that nobody notices until a student sees an empty course.
  await lessonRow.getByRole('button', { name: 'Publish', exact: true }).click();
  // Publishing closes the editor, so the post-condition is the row's badge.
  await expect(lessonRow.getByText('Published')).toBeVisible();

  const moduleCard = page.getByTestId('module-card').filter({ hasText: 'Module one' }).first();
  await moduleCard.getByRole('button', { name: 'Publish', exact: true }).click();
  await expect(moduleCard.getByRole('button', { name: 'Unpublish' })).toBeVisible();

  // The course last: it refuses to publish until a published module holds a
  // published lesson, which is the rule that makes the order matter.
  await page.reload();
  const publishing = page.getByTestId('course-publishing');
  await publishing.getByRole('button', { name: 'Publish', exact: true }).click();
  await expect(publishing.getByText('Published').first()).toBeVisible();

  // ========================================================================
  // 5. Batch, with a timetable turned into real classes
  // ========================================================================
  await page.goto('/admin/batches');
  await page.getByRole('button', { name: 'New batch' }).click();
  await page.getByLabel('Batch name').fill(batchName);
  await selectContaining(page, 'Course', courseTitle);

  const start = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const end = new Date(Date.now() + 83 * 24 * 60 * 60 * 1000);
  await page.getByLabel('Start date').fill(start.toISOString().slice(0, 10));
  await page.getByLabel('End date').fill(end.toISOString().slice(0, 10));
  await page.getByLabel('Capacity').fill('10');
  await page.getByRole('button', { name: /create batch/i }).click();

  // As with the course, creating opens the batch itself.
  await expect(page.getByRole('heading', { name: batchName })).toBeVisible();
  const batchUrl = page.url();
  const batchCode = (await page.getByText(/GRS-B-\d+/).first().innerText()).trim();

  // ========================================================================
  // 6. Assign a trainer, then reassign — one at a time, with handover
  // ========================================================================
  const trainerSelect = page.getByLabel('Assigned trainer');
  // The list is fetched after the page renders, so wait for it rather than
  // reading an empty select and blaming the environment.
  await expect
    .poll(async () => (await trainerSelect.locator('option').count()) > 2, { timeout: 20_000 })
    .toBe(true);
  const trainerValues = await trainerSelect.locator('option').evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLOptionElement).value).filter(Boolean),
  );
  expect(
    trainerValues.length,
    'the environment needs two trainers to reassign between',
  ).toBeGreaterThan(1);

  await trainerSelect.selectOption(trainerValues[0] as string);
  await page.getByRole('button', { name: 'Assign', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: /trainer assigned/i })).toBeVisible();

  // Reassign — to the trainer this journey then signs in as. A trainer only
  // sees the batches they teach, so handing the batch to somebody else and then
  // signing in as `trainer1` would leave them looking at an empty teaching
  // screen for a batch that exists.
  const trainerLookup = await page.request.get(
    `${API}/api/v1/trainers/?search=${encodeURIComponent(TRAINER)}`,
  );
  expect(trainerLookup.ok(), 'could not look up the seeded trainer').toBeTruthy();
  const trainerRows = (await trainerLookup.json()).results as { trainer_id: string }[];
  expect(trainerRows.length, `no seeded trainer matching ${TRAINER}`).toBeGreaterThan(0);
  const teachingCode = trainerRows[0]!.trainer_id;

  await page.reload();
  await selectContaining(page, 'Assigned trainer', teachingCode);
  await page.getByRole('button', { name: 'Assign', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: /trainer assigned/i })).toBeVisible();

  // The timetable, then the classes it implies.
  //
  // Early in the morning, because the trainer already teaches seeded batches
  // through the working day and the overlap guard refuses a clash — correctly,
  // and confusingly for a journey that only wanted a timetable. A fixed slot is
  // safe because the teardown at the end cancels this batch, and a cancelled
  // batch's timetable no longer holds the slot against anyone.
  // The class has to have *started*, or the register refuses to open — which is
  // the correct rule (marking a register in advance records something that has
  // not happened) and an easy one to fall foul of when a suite runs at 02:00.
  // So: the quiet early slot when the day is already past it, and otherwise a
  // window that ended shortly before now.
  const now = new Date();
  const asTime = (at: Date) =>
    `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
  const pastEnough = now.getHours() >= 7;
  const slotStart = pastEnough ? '05:00' : asTime(new Date(now.getTime() - 90 * 60_000));
  const slotEnd = pastEnough ? '06:00' : asTime(new Date(now.getTime() - 30 * 60_000));
  // Today's weekday, so the timetable produces a class today and the register
  // can actually be taken. The register opens only once a class has started,
  // which is why the slot is early in the morning.
  const weekdayNames = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];
  const todayLabel = weekdayNames[(new Date().getDay() + 6) % 7] as string;
  await selectContaining(page, 'Day', todayLabel);
  await page.getByLabel('Start', { exact: true }).fill(slotStart);
  await page.getByLabel('End', { exact: true }).fill(slotEnd);
  await page.getByRole('button', { name: 'Add class' }).click();
  // Assert the class landed. A refused schedule shows an error and leaves the
  // generate button disabled, which is a much harder failure to read.
  await expect(page.getByText(`${slotStart}–${slotEnd}`)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate classes' })).toBeEnabled();
  await page.getByRole('button', { name: 'Generate classes' }).click();
  await expect(page.getByRole('status').filter({ hasText: /class(es)? created/i })).toBeVisible();

  // ========================================================================
  // 7–8. Add a student, and enrol students on the batch
  // ========================================================================
  await page.goto('/admin/students');
  await page.getByRole('button', { name: 'Add student' }).click();
  await page.getByLabel('Email').fill(newStudentEmail);
  await page.getByLabel('First name').fill('Release');
  await page.getByLabel('Last name').fill('Candidate');
  await page.getByRole('button', { name: 'Create student' }).click();
  await expect(page.getByText(newStudentEmail)).toBeVisible();

  await page.goto(batchUrl);
  await selectContaining(page, 'Add a student', 'Release Candidate');
  await page.getByRole('button', { name: 'Enrol', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: /enrol/i })).toBeVisible();

  // And the seeded student, who has a password and can therefore sign in.
  //
  // Found by their student code rather than their name: the picker lists people
  // the way a human reads them ("Riya Verma (GRS-S-00011)"), and the seeded
  // roster's names come from a rotating list, so `student2`'s name is not
  // knowable from their address.
  const studentSearch = await page.request.get(
    `${API}/api/v1/students/?search=${encodeURIComponent(STUDENT)}`,
  );
  expect(studentSearch.ok(), 'could not look up the seeded student').toBeTruthy();
  const found = (await studentSearch.json()).results as { student_id: string }[];
  expect(found.length, `no seeded student matching ${STUDENT}`).toBeGreaterThan(0);
  const seededCode = found[0]!.student_id;

  await page.reload();
  await selectContaining(page, 'Add a student', seededCode);
  await page.getByRole('button', { name: 'Enrol', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: /enrol/i })).toBeVisible();

  await signOut(page);

  // ========================================================================
  // 9–10. The student signs in and starts learning
  // ========================================================================
  await signIn(page, STUDENT);
  await page.goto('/my-learning');
  await expect(page.getByText(courseTitle).first()).toBeVisible();

  // "Continue where you left off" is the front door to a course a student is
  // enrolled on, and on a course with one unread lesson it points at that lesson.
  const continueLink = page
    .locator('[data-testid="continue-learning"]')
    .filter({ hasText: 'Lesson one' })
    .first();
  await expect(continueLink).toBeVisible();
  await continueLink.click();

  await expect(page.getByRole('heading', { name: 'Lesson one' })).toBeVisible();
  await page.getByTestId('lesson-completion').click();
  await expect(page.getByRole('status').filter({ hasText: /marked complete/i })).toBeVisible();

  await signOut(page);

  // ========================================================================
  // 11. The register is taken, and the student can see it
  // ========================================================================
  await signIn(page, TRAINER);
  await page.goto('/teaching');
  await expect(page.getByRole('heading', { name: 'Teaching today' })).toBeVisible();

  // This batch's class, not whichever one the trainer happens to teach first:
  // the whole point is that the student enrolled here is marked present here.
  const todaysClass = page.getByTestId('today-class').filter({ hasText: batchCode }).first();
  await expect(todaysClass).toBeVisible();
  await todaysClass.getByRole('link', { name: /take register|review register/i }).click();

  await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();
  await page.getByRole('button', { name: 'Mark all present' }).click();
  await page.getByRole('button', { name: 'Save register' }).click();
  await expect(page.getByRole('status').filter({ hasText: /saved/i })).toBeVisible();

  // ========================================================================
  // 12–13. Work is set, handed in, and graded
  // ========================================================================
  await page.goto('/teaching/assignments');
  await page.getByRole('button', { name: 'New assignment' }).click();
  await selectContaining(page, 'Batch', batchCode);
  await page.getByLabel('Title').fill(assignmentTitle);
  await page.getByLabel('Instructions').fill('Hand in a source file.');
  await page.getByLabel('Marks out of').fill('50');
  await page.getByRole('button', { name: 'Create assignment' }).click();

  await page.getByRole('link', { name: assignmentTitle }).click();
  // Wait for the detail page before reading its address: `page.url()` returns
  // whatever the browser is showing now, which after a click is often still the
  // list — and a stale URL sends every later step back to the wrong screen.
  await expect(page.getByRole('heading', { name: assignmentTitle })).toBeVisible();
  const assignmentUrl = page.url();
  await page.getByRole('button', { name: 'Publish' }).click();
  await expect(page.getByRole('status')).toContainText(/published/i);
  await signOut(page);

  await signIn(page, STUDENT);
  await page.goto('/my-assignments');
  // This assignment's card, not the first one on the page: a student on more
  // than one batch has other work waiting, and handing a file to whichever form
  // renders first submits it against somebody else's task.
  const work = page.getByTestId('assignment-card').filter({ hasText: assignmentTitle }).first();
  await expect(work, 'the student should see the assignment just published').toBeVisible();
  await work.getByLabel('Files').setInputFiles({
    name: 'answer.py',
    mimeType: 'text/x-python',
    buffer: Buffer.from("print('release journey')\n"),
  });
  await work.getByRole('button', { name: 'Submit' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: /submitted|handed in/i }),
  ).toBeVisible();
  await signOut(page);

  await signIn(page, TRAINER);
  await page.goto(assignmentUrl);
  // The row for the student who actually handed something in: the rest of the
  // cohort is on the same list with nothing to mark.
  const marking = page
    .getByRole('table')
    .locator('tbody tr')
    .filter({ has: page.getByLabel('Marks') })
    .first();
  await expect(marking).toBeVisible();
  await marking.getByLabel('Marks').fill('45');
  await marking.getByLabel('Feedback').fill('Correct and readable.');
  await marking.getByRole('button', { name: 'Save grade' }).click();
  await expect(page.getByRole('status')).toContainText(/graded/i);

  // ========================================================================
  // 14–15. A weekly test result is imported, and the student sees it
  // ========================================================================
  await page.goto('/teaching/assessments');
  await page.getByRole('button', { name: 'New test' }).click();
  await selectContaining(page, 'Batch', batchCode);
  await page.getByLabel('Title').fill(testTitle);
  // Taken in class: an externally delivered test needs a link, and this journey
  // is about importing the marks rather than about where they were earned.
  await selectContaining(page, 'How it is taken', 'Offline');
  await page.getByLabel('Marks out of').fill('20');
  await page.getByRole('button', { name: 'Create test' }).click();

  await page.getByRole('link', { name: testTitle }).click();
  await expect(page.getByRole('heading', { name: 'Import results' })).toBeVisible();
  const publish = page.getByRole('button', { name: 'Publish' });
  if (await publish.count()) {
    await publish.first().click();
    await expect(page.getByRole('status')).toContainText(/published/i);
  }

  const codes = await page
    .getByRole('table')
    .locator('tbody tr td:first-child .font-mono')
    .allInnerTexts();
  expect(codes.length, 'the marks sheet should list the enrolled cohort').toBeGreaterThan(0);

  const csv = ['student_id,marks', ...codes.map((code) => `${code.trim()},17`)].join('\n');
  await page.getByLabel('Result file').setInputFiles({
    name: 'results.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  });
  await page.getByRole('button', { name: 'Preview import' }).click();
  const preview = page.getByTestId('import-preview');
  await expect(preview).toBeVisible();
  await preview.getByRole('button', { name: 'Confirm import' }).click();
  await expect(page.getByRole('status')).toContainText(/imported/i);
  await signOut(page);

  await signIn(page, STUDENT);
  await page.goto('/my-results');
  await expect(page.getByTestId('result-row').first()).toBeVisible();
  await signOut(page);

  // ========================================================================
  // 16–18. A project is set, handed in, and reviewed
  // ========================================================================
  await signIn(page, TRAINER);
  await page.goto('/teaching/projects');
  await page.getByRole('button', { name: 'New project' }).click();
  await selectContaining(page, 'Batch', batchCode);
  await page.getByLabel('Title').fill(projectTitle);
  await page.getByLabel('Description').fill('Build something small and useful.');
  await page.getByLabel('Deliverables').fill('Source and a README.');
  await page.getByLabel('Marks out of').fill('100');
  await page.getByRole('button', { name: 'Create project' }).click();

  await page.getByRole('link', { name: projectTitle }).click();
  await expect(page.getByRole('heading', { name: projectTitle })).toBeVisible();
  const projectUrl = page.url();
  await page.getByRole('button', { name: 'Publish' }).click();
  await expect(page.getByRole('status')).toContainText(/published/i);
  await page.getByRole('button', { name: 'Assign to the cohort' }).click();
  await expect(page.getByRole('status')).toContainText(/assigned/i);
  await signOut(page);

  await signIn(page, STUDENT);
  await page.goto('/my-projects');
  const card = page.getByTestId('project-card').filter({ hasText: projectTitle });
  await expect(card).toBeVisible();
  await card.getByLabel('Files').setInputFiles({
    name: 'tool.py',
    mimeType: 'text/x-python',
    buffer: Buffer.from("print('my tool')\n"),
  });
  await card.getByRole('button', { name: 'Hand in' }).click();
  await expect(page.getByRole('status')).toContainText(/handed in/i);
  await signOut(page);

  await signIn(page, TRAINER);
  await page.goto(projectUrl);
  const queue = page
    .getByRole('table')
    .locator('tbody tr')
    .filter({ hasText: 'Submitted' })
    .first();
  await expect(queue).toBeVisible();
  await queue.getByLabel('Marks').fill('88');
  await queue.getByLabel('Feedback').fill('Clean, well documented.');
  await queue.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByRole('status')).toContainText(/approved/i);
  await signOut(page);

  // ========================================================================
  // 19–20. An examination is sat, and the server calculates the result
  // ========================================================================
  await signIn(page, ADMIN);
  await page.goto('/teaching/questions');
  for (const [index, text] of [
    'What does a shell do?',
    'Name one way to list files.',
    'What is a working directory?',
  ].entries()) {
    await page.getByRole('button', { name: 'New question' }).click();
    await selectContaining(page, 'Batch', batchCode);
    // Short answer on purpose: it is the type the server cannot mark on its
    // own, so the examination that draws these questions exercises the
    // manual-marking path as well as the automatic one.
    await selectContaining(page, 'Type', 'Short answer');
    await page.getByLabel('Question', { exact: true }).fill(text);
    await page.getByLabel('Accepted answers').fill(`answer ${index}`);
    await page.getByLabel('Marks', { exact: true }).fill('5');
    await page.getByRole('button', { name: 'Add to the bank' }).click();
    await expect(page.getByText(text).first()).toBeVisible();
  }

  await page.goto('/teaching/exams');
  await page.getByRole('button', { name: 'New examination' }).click();
  await selectContaining(page, 'Batch', batchCode);
  await page.getByLabel('Title', { exact: true }).fill(examTitle);
  await page.getByLabel('Duration in minutes').fill('45');
  await page.getByLabel('Attempts allowed').fill('1');
  await page.getByLabel('Opens').fill(localDateTime(-5));
  await page.getByLabel('Closes').fill(localDateTime(60 * 24));
  await page.getByLabel('Questions to draw').fill('3');
  await page.getByRole('button', { name: 'Create examination' }).click();

  await page.getByRole('link', { name: examTitle }).click();
  await expect(page.getByRole('heading', { name: examTitle })).toBeVisible();
  const examUrl = page.url();
  await page.getByRole('button', { name: 'Publish' }).click();
  await expect(page.getByRole('status')).toContainText(/published/i);
  await signOut(page);

  await signIn(page, STUDENT);
  await page.goto('/exams');
  const examCard = page.getByTestId('exam-card').filter({ hasText: examTitle });
  await expect(examCard).toBeVisible();
  await examCard.getByRole('link', { name: /start the examination/i }).click();

  const questions = page.getByTestId('exam-question');
  await expect(questions.first()).toBeVisible();
  const questionCount = await questions.count();
  for (let index = 0; index < questionCount; index += 1) {
    const question = questions.nth(index);
    const choice = question.locator('input[type="radio"], input[type="checkbox"]').first();
    if (await choice.count()) {
      await choice.check();
    } else {
      await question.getByRole('textbox').fill(`answer ${index}`);
      await question.getByRole('textbox').blur();
    }
  }
  await page.getByRole('button', { name: 'Submit my paper' }).click();
  await expect(page.getByRole('status')).toContainText(/submitted/i);
  await signOut(page);

  // Anything the server could not mark on its own is marked by a human, then
  // the results are released. The score is the server's either way.
  await signIn(page, TRAINER);
  await page.goto(examUrl);
  const awaiting = page.getByRole('heading', { name: /answers awaiting marking \((\d+)\)/i });
  if (await awaiting.count()) {
    const label = await awaiting.innerText();
    const outstanding = Number(label.match(/\((\d+)\)/)?.[1] ?? 0);
    for (let index = 0; index < outstanding; index += 1) {
      const row = page.getByTestId('manual-answer').first();
      await row.getByLabel('Awarded').fill('5');
      await row.getByRole('button', { name: /save|award/i }).click();
      await expect(page.getByRole('status')).toBeVisible();
    }
  }
  const release = page.getByRole('button', { name: /release results/i });
  if (await release.count()) {
    await release.first().click();
    await expect(page.getByRole('status')).toContainText(/released/i);
  }
  await signOut(page);

  // ========================================================================
  // 21–22. Completion is evaluated and approved; a certificate is issued
  // ========================================================================
  await signIn(page, ADMIN);
  await page.goto('/admin/completions');
  await selectContaining(page, 'Batch', batchCode);
  // Every status, not just the default: a student who has finished everything
  // should be eligible, and filtering to "eligible" before checking would hide
  // the interesting failure — a cohort that finished the work and did not
  // qualify — behind an empty list.
  await page.getByRole('combobox', { name: 'Status' }).selectOption('');

  // Evaluate the cohort. A completion is a decision, not a side effect of
  // grading: nothing writes one until somebody asks the rules to be applied,
  // which is why this button exists and why the queue is empty without it.
  await page.getByRole('button', { name: 'Re-evaluate this batch' }).click();
  await expect(page.getByRole('status').filter({ hasText: /re-evaluated/i })).toBeVisible();

  // The student who actually did the work, not whoever sorts first: this batch
  // also holds the newly created account, which was enrolled to prove that step
  // and has handed nothing in.
  const row = page.getByTestId('completion-row').filter({ hasText: seededCode }).first();
  await expect(row, 'the batch should have a completion record after the work was done').toBeVisible();
  await row.getByRole('button', { name: 'Show the rules' }).click();
  await expect(row.getByTestId('completion-rules')).toBeVisible();

  await row.getByLabel('Note').fill('Checked against the register and the marks.');
  const approve = row.getByRole('button', { name: 'Approve' });
  await expect(approve, 'the student must be eligible after finishing everything').toBeEnabled();
  await approve.click();
  await expect(page.getByRole('status')).toContainText(/approved/i);

  await page.getByRole('combobox', { name: 'Status' }).selectOption('approved');
  const approved = page.getByTestId('completion-row').filter({ hasText: seededCode }).first();
  await approved.getByRole('button', { name: 'Issue the certificate' }).click();
  await expect(page.getByRole('status')).toContainText(/certificate issued/i);

  await page.goto('/admin/certificates');
  const certificate = page.getByTestId('certificate-row').first();
  await expect(certificate).toContainText('GRS-CERT-');

  // ========================================================================
  // 23. Public verification, signed out — the way an employer checks one
  // ========================================================================
  //
  // The address comes from the student's own progress page, because that is
  // where a graduate finds it. Verification is keyed on a verification code
  // rather than the certificate number: the number identifies the document, the
  // code is what may safely be published.
  await signOut(page);
  await signIn(page, STUDENT);
  await page.goto('/my-progress');

  const verifyLink = page.locator('a[href^="/verify/"]').first();
  await expect(verifyLink, 'the student should be shown where to verify it').toBeVisible();
  const verifyPath = await verifyLink.getAttribute('href');
  expect(verifyPath).toBeTruthy();

  await signOut(page);
  await page.goto(verifyPath as string);
  await expect(page.getByTestId('verification-verdict')).toContainText(/valid certificate/i);
  await expect(page.getByTestId('verified-student')).toBeVisible();
  await expect(page.getByTestId('verified-course')).toContainText(courseTitle);

  // ========================================================================
  // Teardown — so the journey can run again tomorrow against the same stack
  // ========================================================================
  await signIn(page, ADMIN);
  await page.goto(assignmentUrl);
  await page.getByRole('button', { name: 'Archive' }).click();
  await page.goto(projectUrl);
  await page.getByRole('button', { name: 'Archive' }).click();
  await page.goto(courseUrl);
  await page.getByRole('button', { name: 'Archive' }).click();
  await expect(page.getByText('Archived').first()).toBeVisible();

  // Cancel the batch. Not tidiness: an active batch keeps its timetable slot
  // reserved against the trainer, so the next run of this journey could not
  // book the same hour. Cancelling releases it, which is exactly what the
  // conflict rule says a cancelled batch does.
  await page.goto(batchUrl);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Cancelled').first()).toBeVisible();
});
