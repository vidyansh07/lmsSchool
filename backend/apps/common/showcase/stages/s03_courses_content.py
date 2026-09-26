"""What stage 3 writes: the catalogue, spelled out.

The stage module (:mod:`.s03_courses`) is the *how* — which service, in which
order, found by which key. This module is the *what*: the categories, the
eight showcase courses with their modules and lessons, the material the
imported SITP tracks get, and the question bank. It is data, not logic, kept
apart so that a person changing a lesson's wording never touches the
find-or-create code and a person fixing the find-or-create code never scrolls
through forty paragraphs of Linux.

Everything here is written out rather than generated, for the same reason the
roster is: a demo whose course titles change between deploys is a demo nobody
can write a walkthrough for. The one generated part — the three lessons each
imported SITP track receives — is generated from a per-track profile so the
text names that track's tools and topics, and is the same text on every run.

Slugs are the natural keys the stage finds rows by, so they are chosen once
and do not change; retitling a lesson is fine, re-slugging it would create a
second lesson next to the first.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.courses.models import (
    CourseAuthorRole,
    CourseDifficulty,
    CourseVisibility,
    LessonContentType,
    PublishStatus,
)
from apps.questions.models import Difficulty, QuestionType

#: Reserved by RFC 2606: the links never resolve, which is the point.
DOCS_HOST = "https://docs.example.invalid"

#: What the SITP workbook import titles every course it creates.
SITP_PREFIX = "SITP ACE 2026"

#: The course that carries the course-level academic policy, and its rules —
#: stricter attendance than the institution's 75 %, because a Red Hat exam
#: candidate who misses a fifth of the labs does not pass EX200.
POLICY_COURSE = "rhcsa"
POLICY_RULES = {"minimum_attendance_percent": Decimal("80.00")}


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LessonSpec:
    """One lesson. ``body`` is the text for a text lesson and the handout's
    text for a document lesson; ``url`` is the target of an external link."""

    kind: str
    title: str
    slug: str
    body: str = ""
    url: str = ""
    minutes: int = 30
    description: str = ""
    status: str = PublishStatus.PUBLISHED
    preview: bool = False
    optional: bool = False
    #: ``(title, https url)`` link resources attached to the lesson.
    links: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ModuleSpec:
    title: str
    description: str
    lessons: tuple[LessonSpec, ...]
    status: str = PublishStatus.PUBLISHED


@dataclass(frozen=True)
class CourseSpec:
    slug: str
    title: str
    category: str
    difficulty: str
    visibility: str
    fee: Decimal
    minutes: int
    short: str
    description: str
    objectives: tuple[str, ...]
    prerequisites: tuple[str, ...]
    status: str
    #: ``(roster local part, CourseAuthorRole)``; skipped when the trainer is
    #: not on the database yet (a ``--only courses`` run before ``people``).
    authors: tuple[tuple[str, str], ...]
    modules: tuple[ModuleSpec, ...]


def text(title: str, slug: str, body: str, minutes: int = 40, **extra) -> LessonSpec:
    return LessonSpec(LessonContentType.TEXT, title, slug, body=body, minutes=minutes, **extra)


def video(title: str, slug: str, minutes: int = 25, **extra) -> LessonSpec:
    return LessonSpec(LessonContentType.VIDEO, title, slug, minutes=minutes, **extra)


def document(title: str, slug: str, body: str, minutes: int = 20, **extra) -> LessonSpec:
    return LessonSpec(LessonContentType.DOCUMENT, title, slug, body=body, minutes=minutes, **extra)


def link(title: str, slug: str, url: str, minutes: int = 15, **extra) -> LessonSpec:
    return LessonSpec(
        LessonContentType.EXTERNAL_LINK, title, slug, url=url, minutes=minutes, **extra
    )


# ---------------------------------------------------------------------------
# Categories: (slug, name, description, position, active)
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, str, str, int, bool]] = [
    (
        "linux-devops",
        "Linux & DevOps",
        "Red Hat system administration, containers, orchestration and automation.",
        10,
        True,
    ),
    (
        "cloud",
        "Cloud Computing",
        "AWS and Azure certification tracks and cloud architecture.",
        20,
        True,
    ),
    ("programming", "Programming", "Languages, frameworks and full-stack development.", 30, True),
    (
        "data-science",
        "Data Science",
        "Python for data, statistics, machine learning and analytics tooling.",
        40,
        True,
    ),
    (
        "cyber-security",
        "Cyber Security",
        "Ethical hacking, defensive security and SOC operations.",
        50,
        True,
    ),
    (
        "networking",
        "Networking",
        "Cisco routing and switching, and network fundamentals.",
        60,
        True,
    ),
    (
        "hardware-repair",
        "Hardware & Repair",
        "Laptop and desktop repair. No longer offered; kept for the records of past batches.",
        90,
        False,
    ),
]


# ---------------------------------------------------------------------------
# The eight showcase courses
# ---------------------------------------------------------------------------

_RHCSA_MODULES = (
    ModuleSpec(
        "Getting around a Red Hat system",
        "The shell, the file system and the manual: everything else builds on this.",
        (
            text(
                "The Linux shell and the file system tree",
                "shell-and-file-system",
                """
# The shell and the file system tree

Every Red Hat system starts you in a shell, usually bash, and every exam task
is done from it. The prompt tells you who you are and where you are:
`[student@servera ~]$` is a normal user in their home directory, while
`[root@servera /etc]#` is the superuser sitting in `/etc`. The `~` and the `#`
are the two things to check before running anything destructive.

The file system is one tree rooted at `/`. `/etc` holds configuration,
`/var` holds data that grows (logs, mail, databases), `/usr` holds the
installed software, `/home` holds users, and `/tmp` is cleared on reboot.
Devices appear as files under `/dev`, and the kernel's live view of the
machine is under `/proc` and `/sys`. Nothing is "on drive C": a second disk
is mounted *into* the tree at a directory you choose.

Four commands cover most of the moving around: `pwd` (where am I), `ls -l`
(what is here, with permissions), `cd` (go somewhere) and `man` (how does this
work). Learn `man -k keyword` early — the exam does not allow the internet,
but it does allow the manual pages.
""",
                preview=True,
                description=(
                    "A free preview: how a Red Hat system is laid out and how to move around it."
                ),
            ),
            video("Users, groups and sudo", "users-groups-sudo", minutes=32),
            document(
                "Lab: create users and set permissions",
                "lab-users-permissions",
                """
Lab sheet. Work on servera as root. Create the groups devops and audit; create
the users priya, arjun and meena with priya and arjun in devops and meena in
audit. Set priya's password to expire in 30 days. Create /srv/shared owned by
root:devops with mode 2770 so files created inside inherit the group. Verify
with ls -ld and with a file created as arjun. Finally, give the devops group
permission to run systemctl restart httpd through sudo without a password, and
prove it works as priya.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Storage and services",
        "Partitions, LVM, file systems, and the services that run on top of them.",
        (
            text(
                "Logical Volume Manager from the ground up",
                "lvm-from-the-ground-up",
                """
# Logical Volume Manager

LVM puts a layer between the disks and the file systems so that a volume can
grow later without a reinstall. Three objects, in order: a *physical volume*
is a disk or partition initialised with `pvcreate`; a *volume group* pools
one or more physical volumes with `vgcreate`; a *logical volume* is carved out
of a volume group with `lvcreate` and is what you format and mount.

The commands echo the object names, which makes them easy to remember:
`pvs`, `vgs` and `lvs` list; `pvcreate`, `vgcreate` and `lvcreate` make;
`vgextend` and `lvextend` grow. After extending a logical volume the file
system on it must be grown too — `xfs_growfs` for XFS, `resize2fs` for ext4 —
or `df` will show the old size and you will wonder where the space went.

Sizes can be given in extents (`-l`) or bytes (`-L 2G`); the extent size is
fixed when the volume group is created, defaulting to 4 MiB. On the exam,
check `vgdisplay` for free extents before promising a size you do not have.
""",
            ),
            video("Mounting file systems persistently with fstab", "fstab-persistent-mounts"),
            link(
                "Red Hat documentation: managing file systems",
                "rhel-storage-docs",
                f"{DOCS_HOST}/rhel/9/managing-file-systems",
                description="The vendor's own guide to the commands covered in this module.",
            ),
        ),
    ),
    ModuleSpec(
        "SELinux, firewalld and the exam",
        "The two things that stop a working service from answering, and how the day itself runs.",
        (
            text(
                "SELinux: contexts, booleans and the audit log",
                "selinux-contexts-booleans",
                """
# SELinux

SELinux labels every process and every file with a *context* and allows an
access only when policy says the two labels may meet. A web server labelled
`httpd_t` may read files labelled `httpd_sys_content_t` and nothing else — so
a page copied from a home directory, still labelled `user_home_t`, gives a 403
even though the Unix permissions are fine. `ls -Z` and `ps -Z` show contexts.

Fix a wrong label with `restorecon -Rv /path`, which reapplies the label the
policy expects. For a directory outside the defaults, teach the policy first:
`semanage fcontext -a -t httpd_sys_content_t "/srv/web(/.*)?"` and then
`restorecon`. Never set the mode to permissive to make an exam task pass; the
grader checks that enforcing is still on.

Booleans switch whole behaviours: `setsebool -P httpd_can_network_connect on`
lets the web server open outbound connections. When something is denied and
you do not know why, `ausearch -m AVC -ts recent` reads the audit log, and
`sealert` (from setroubleshoot-server) explains it in words.
""",
                links=(
                    ("SELinux user guide", f"{DOCS_HOST}/rhel/9/using-selinux"),
                    ("firewalld reference", f"{DOCS_HOST}/rhel/9/firewalld"),
                ),
            ),
            document(
                "EX200 objectives checklist",
                "ex200-objectives-checklist",
                """
The published EX200 objectives, grouped the way this course teaches them.
Tick each one off only when you can do it without looking anything up.
Essential tools: shell, redirection, grep, archives, file permissions, man.
Shell scripts: loops, conditionals, exit codes. Operate running systems: boot
targets, reset root password, process priority, journald, tuned. Storage: LVM,
XFS and ext4, fstab, swap, Stratis is not examined. Users and groups: creation,
password ageing, sudo, group collaboration. Security: SELinux enforcing, file
contexts, booleans, firewalld zones and services, ssh keys. Containers: podman
pull/run, rootless containers as a systemd user service with loginctl
enable-linger.
""",
                optional=True,
                description="Supplementary: the official objective list, annotated.",
            ),
            video("Exam day walkthrough", "exam-day-walkthrough", minutes=18),
        ),
    ),
)

_DEVOPS_MODULES = (
    ModuleSpec(
        "Containers with Docker",
        "Images, containers, volumes and networks — the vocabulary every later tool assumes.",
        (
            text(
                "Why containers, and what an image actually is",
                "why-containers",
                """
# Why containers

A container is a normal Linux process with a restricted view of the machine:
its own file system, its own process tree, its own network interface. It is
not a virtual machine — there is no second kernel — which is why a container
starts in milliseconds and a host can run hundreds of them. The isolation
comes from two kernel features, namespaces (what the process can *see*) and
cgroups (what it may *use*).

An image is the read-only file system a container starts from, built up in
layers. Each instruction in a Dockerfile adds a layer, and layers are shared
between images that begin the same way, so twenty images based on
`python:3.12-slim` store the base once. When a container writes a file, the
write lands in a thin writable layer on top and disappears with the container
— which is why anything that must survive goes in a volume.

Order your Dockerfile from least to most frequently changed: base image,
system packages, dependency manifest, dependencies, then your code. A change
to a line invalidates the cache for every line below it, so putting `COPY . .`
before `pip install` means reinstalling everything on every commit.
""",
                preview=True,
            ),
            video("Writing a production Dockerfile", "production-dockerfile", minutes=35),
            document(
                "Lab: containerise the fee-ledger service",
                "lab-containerise-service",
                """
Build a multi-stage image for the sample Django service in the lab repository.
Stage one installs build tools and compiles the wheels; stage two copies only
the wheels and the source onto python:3.12-slim, creates an unprivileged user,
and sets the entrypoint to gunicorn. Target an image under 200 MB. Run it with
a named volume for the media directory and a bridge network shared with a
postgres:16 container. Prove the data survives docker rm by recreating the
database container and listing the tables again.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Kubernetes",
        "Pods, Deployments, Services and the control loop that keeps them true.",
        (
            text(
                "The Kubernetes control loop",
                "kubernetes-control-loop",
                """
# The control loop

Kubernetes is a set of controllers each doing one thing forever: read the
desired state from the API server, observe the actual state, and take one
step to close the gap. You do not tell Kubernetes to *start three pods*; you
declare that a Deployment should have three replicas, and the Deployment
controller creates a ReplicaSet, the ReplicaSet controller creates Pods, and
the scheduler places each Pod on a node with room for it. Kill a Pod and the
loop notices the count is two and makes a third.

Everything is an object with `apiVersion`, `kind`, `metadata` and `spec`, and
`kubectl apply -f` sends the object to the API server, which stores it in
etcd. `kubectl get`, `describe` and `logs` are how you read back what the
controllers did; `kubectl explain deployment.spec.strategy` reads the schema
without leaving the terminal.

A Service gives a stable name and virtual IP to a set of Pods chosen by
label selector, because Pod IPs change every time a Pod is replaced. ClusterIP
is reachable inside the cluster, NodePort opens a port on every node, and an
Ingress routes HTTP by host and path to Services behind it.
""",
            ),
            video("Deployments, rollouts and rollbacks", "deployments-rollouts", minutes=40),
            link(
                "Kubernetes reference: workloads",
                "kubernetes-workloads-reference",
                f"{DOCS_HOST}/kubernetes/concepts/workloads",
            ),
        ),
    ),
    ModuleSpec(
        "Automation with Ansible and CI/CD",
        "Playbooks, roles, and a pipeline that builds, tests and deploys on every push.",
        (
            text(
                "Ansible playbooks: idempotent by design",
                "ansible-playbooks-idempotent",
                """
# Playbooks

An Ansible playbook is a list of plays, each mapping a group of hosts to a
list of tasks, and each task calling one module with arguments. The modules
are what make Ansible pleasant: `package: name=httpd state=present` installs
httpd if it is missing and does nothing if it is there, and reports which
happened. Run the playbook twice and the second run changes nothing — that is
idempotence, and a playbook that is not idempotent is a shell script with
extra steps.

Inventory lists the hosts and their groups, in INI or YAML, and variables
attach at every level: group_vars, host_vars, the play, the task, and the
command line with `-e`. When two definitions collide, the more specific wins,
and the precedence table in the documentation is the one page worth
memorising.

Handlers run once at the end of a play, only if a task notified them, which
is how "restart nginx" happens once after three config files change rather
than three times. Roles package tasks, handlers, templates and defaults into a
directory layout that `ansible-galaxy init` creates for you.
""",
                links=(("Ansible module index", f"{DOCS_HOST}/ansible/collections/index"),),
            ),
            document(
                "Pipeline design worksheet",
                "pipeline-design-worksheet",
                """
Design a pipeline for the lab service with five stages: lint, unit tests,
image build, image scan and deploy to staging. For each stage write down the
trigger, the tool, the artefact it produces, what makes it fail, and how long
it may take before somebody should be paged. Mark the stages that can run in
parallel. Then decide: does a failed image scan block the deploy, or only warn?
Justify the answer in two sentences and bring it to the review session.
""",
                optional=True,
            ),
            video("GitLab CI from zero to deployed", "gitlab-ci-zero-to-deployed", minutes=45),
        ),
    ),
    ModuleSpec(
        "Observability with Prometheus and Grafana",
        "Being written: metrics, alerting rules and dashboards for the lab cluster.",
        (
            text(
                "Metrics, logs and traces: the three signals",
                "three-signals",
                """
# Draft — the three signals

Metrics are numbers over time, cheap to store and ideal for alerting. Logs
are events with context, expensive at volume and ideal for explaining a
metric. Traces follow one request across services. This module will cover
Prometheus for the first, Loki for the second and OpenTelemetry for the
third; the lab environment is being rebuilt with the operator installed.
""",
                status=PublishStatus.DRAFT,
            ),
        ),
        status=PublishStatus.DRAFT,
    ),
    ModuleSpec(
        "Docker Swarm (retired)",
        "Retired from the syllabus in 2024; kept so past batches can still open it.",
        (
            text(
                "Swarm services and the routing mesh",
                "swarm-services-routing-mesh",
                """
# Swarm services

Docker Swarm turns a group of Docker hosts into one scheduler. `docker swarm
init` creates a manager, workers join with a token, and `docker service
create --replicas 3` schedules a task on each. The routing mesh publishes a
port on every node whether or not a task runs there. This material is
retained for reference; the syllabus now teaches Kubernetes.
""",
            ),
        ),
        status=PublishStatus.ARCHIVED,
    ),
)

_PYTHON_MODULES = (
    ModuleSpec(
        "Python foundations",
        "Syntax, data structures and the standard library, taught through small programs.",
        (
            text(
                "Variables, types and the REPL",
                "variables-types-repl",
                """
# Variables, types and the REPL

Python is read top to bottom and run as it is read, and the quickest way to
learn it is to type at it. Start `python3`, and the `>>>` prompt evaluates
whatever you enter: `2 + 3` prints `5`, `"Grras" * 2` prints `'GrrasGrras'`,
and `type(3.0)` tells you it is a float. A variable is a name bound to a
value with `=`; it has no declared type, but the value does, and `int`,
`float`, `str`, `bool`, `list`, `dict` and `None` cover most of what you will
meet this month.

Indentation is not decoration. The body of an `if`, a `for` or a `def` is
whatever is indented beneath it, four spaces by convention, and a block ends
when the indentation ends. Editors handle this for you; the REPL does not, so
finish a block with an empty line.

Strings are immutable sequences of characters, and f-strings are how you put
values in them: `f"Fee due: ₹{amount:,.2f}"` formats a number with a thousands
separator and two decimals. Lists are ordered and mutable, tuples ordered and
fixed, dictionaries map keys to values, and sets hold unique items. Choosing
the right one is most of what "Pythonic" means.
""",
                preview=True,
            ),
            video("Functions, modules and packages", "functions-modules-packages", minutes=38),
            document(
                "Exercise sheet: collections",
                "exercise-sheet-collections",
                """
Twelve exercises on lists, dictionaries and sets, to be done without a
library. 1. Count words in a paragraph. 2. Invert a dictionary. 3. Find the
students who attended both Monday and Tuesday from two lists. 4. Group a list
of (name, city) pairs by city. 5. Remove duplicates while keeping order.
6. Flatten a list of lists. 7. Merge two sorted lists. 8. Find the second
largest number. 9. Compute a running total. 10. Rotate a list by k. 11. Check
whether two strings are anagrams. 12. Build a frequency table and print the
top three. Submit as a single .py file with a function per exercise.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Django: models, views and templates",
        "The request cycle, the ORM and the admin — building the student portal from scratch.",
        (
            text(
                "The request cycle and URL routing",
                "request-cycle-url-routing",
                """
# The request cycle

A request arrives at the WSGI server, Django matches its path against the
patterns in `urls.py` from top to bottom, and the first match calls a view
with the request and any captured values. The view does whatever the page
needs — usually a query through the ORM — and returns a response, most often
a rendered template. Middleware wraps the whole thing: sessions,
authentication and CSRF protection each see the request on the way in and the
response on the way out.

`path("students/<int:pk>/", views.student_detail, name="student-detail")`
captures an integer and passes it as `pk`. Naming the pattern matters: the
template writes `{% url 'student-detail' student.pk %}` and never hard-codes
`/students/12/`, so the path can change in one place.

Function views are fine for a page; class-based views earn their keep for
lists and forms, where `ListView` and `CreateView` implement the boilerplate
and you override only what differs. Start with functions, move to classes
when you find yourself copying one.
""",
            ),
            video("Models, migrations and the ORM", "models-migrations-orm", minutes=42),
            link(
                "Django documentation: making queries",
                "django-queries-docs",
                f"{DOCS_HOST}/django/5.0/topics/db/queries",
            ),
        ),
    ),
    ModuleSpec(
        "REST APIs and deployment",
        "Django REST Framework, authentication, and putting the project on a server.",
        (
            text(
                "Serializers and viewsets in Django REST Framework",
                "drf-serializers-viewsets",
                """
# Serializers and viewsets

A serializer does two jobs: it turns a model instance into JSON and it
validates incoming JSON into a model instance. `ModelSerializer` reads the
model's fields and writes both directions for you; you list the fields to
expose and add `validate_<field>` methods for the rules the model does not
already enforce. Keep business rules out of serializers — a rule that lives
in the serializer is a rule the admin and the management command will not
apply.

A viewset groups the list, retrieve, create, update and destroy actions for
one resource, and a router turns it into URLs. `permission_classes` decide
who may call which action, and `get_queryset` is where a counsellor sees
only their own centre's students rather than everyone's.

Pagination, filtering and throttling are settings, not code: set them once
in `REST_FRAMEWORK` and every endpoint behaves the same. Browse the API in
the browsable renderer while developing, and switch it off in production.
""",
                links=(("DRF tutorial", f"{DOCS_HOST}/drf/tutorial/quickstart"),),
            ),
            document(
                "Deployment checklist for a Django project",
                "django-deployment-checklist",
                """
Before the first deploy: DEBUG off, ALLOWED_HOSTS set, SECRET_KEY from the
environment, database URL from the environment, static files collected and
served by nginx or WhiteNoise, media on a volume or object storage, gunicorn
behind nginx with a systemd unit, HTTPS via certbot, logging to stdout,
migrations run as a deploy step, a health endpoint, and a backup that has
actually been restored once. Run manage.py check --deploy and fix every
warning it prints.
""",
                optional=True,
            ),
            video(
                "Deploying to a Linux server with gunicorn and nginx",
                "deploy-gunicorn-nginx",
                minutes=36,
            ),
        ),
    ),
)

_AWS_MODULES = (
    ModuleSpec(
        "Compute, storage and networking",
        "EC2, S3, EBS and the VPC — the building blocks the exam assumes fluency in.",
        (
            text(
                "Regions, availability zones and the VPC",
                "regions-azs-vpc",
                """
# Regions, availability zones and the VPC

A region is a geography — Mumbai (ap-south-1), Singapore, Virginia — and
inside it are availability zones: separate data centres close enough for
synchronous replication and far enough apart that one flood does not take
both. Architecting for availability means spreading across zones; for
disaster recovery, across regions. Most services are regional, a few (IAM,
Route 53, CloudFront) are global.

A VPC is your own network inside a region: a CIDR block, subnets within it
(each in exactly one zone), route tables that say where traffic goes, and an
internet gateway if anything is to reach the outside. A *public* subnet is
one whose route table sends 0.0.0.0/0 to the internet gateway; a private one
sends it to a NAT gateway or nowhere. Security groups are stateful firewalls
on instances; network ACLs are stateless ones on subnets, and the exam loves
asking which is which.

The default VPC is fine for a lab and wrong for production. Build one from
scratch once with two public and two private subnets across two zones, and
the exam's networking questions become recognisable.
""",
                preview=True,
            ),
            video("EC2 instance types, pricing and placement", "ec2-types-pricing", minutes=30),
            document(
                "Lab: three-tier VPC",
                "lab-three-tier-vpc",
                """
Build a VPC 10.20.0.0/16 in ap-south-1 with public subnets in 1a and 1b, private
application subnets in both, and private database subnets in both. Attach an
internet gateway, a NAT gateway in 1a, and route tables so only the public
subnets reach the internet directly. Launch a t3.micro in a public subnet as a
bastion, a t3.micro in a private application subnet, and prove you can reach
the second only through the first. Record the security group rules you needed
and nothing more.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Identity, databases and resilience",
        "IAM done properly, RDS and DynamoDB, and the patterns that keep a service up.",
        (
            text(
                "IAM: principals, policies and least privilege",
                "iam-least-privilege",
                """
# IAM

Every call to AWS is made by a principal — a user, a role, or a service —
and allowed or denied by the policies attached to it. A policy is a JSON
document of statements, each with an Effect, a list of Actions, a list of
Resources and optional Conditions. An explicit Deny anywhere wins; otherwise
an Allow is needed; otherwise the call is denied. That three-line rule
answers more exam questions than any other single fact.

Roles are how anything other than a person gets permissions. An EC2 instance
assumes a role through its instance profile, a Lambda function through its
execution role, and a person from another account through STS. Long-lived
access keys on an instance are the thing the exam wants you to replace with a
role every time it mentions them.

Least privilege is a practice, not a setting: start from the managed
read-only policy, add the specific actions the workload actually makes, scope
the resources by ARN, and use Access Analyzer to find what was never used.
""",
            ),
            video("RDS Multi-AZ, read replicas and Aurora", "rds-multi-az-replicas", minutes=34),
            link(
                "AWS Well-Architected Framework",
                "well-architected-framework",
                f"{DOCS_HOST}/aws/wellarchitected/latest/framework",
            ),
        ),
    ),
    ModuleSpec(
        "Serverless, cost and the exam",
        "Lambda, API Gateway, SQS, and how to answer a scenario question.",
        (
            text(
                "Reading a scenario question",
                "reading-scenario-questions",
                """
# Reading a scenario question

An SAA-C03 question is a paragraph describing a company, a constraint, and a
request, followed by four architectures. The paragraph contains one or two
words that decide the answer — *most cost-effective*, *least operational
overhead*, *within 15 minutes*, *globally* — and the four options are written
so that three each violate one of them. Underline the qualifiers before
reading the options.

"Least operational overhead" means managed over self-managed: Aurora over
PostgreSQL on EC2, Fargate over EC2 for containers, S3 over anything for
static files. "Most cost-effective" with tolerance for interruption means
Spot; with a steady baseline means Savings Plans. "Real-time" points to
Kinesis or a stream, "decouple" to SQS, "fan out" to SNS. When two options
both work, the one with fewer components is usually the intended answer.

Time: 130 minutes for 65 questions is two minutes each. Flag and move on at
three; the flagged ones are answered with the remaining time and a clearer
head.
""",
                links=(
                    ("Exam guide SAA-C03", f"{DOCS_HOST}/aws/certification/saa-c03-exam-guide"),
                ),
            ),
            document(
                "Service comparison tables",
                "service-comparison-tables",
                """
Quick-reference tables for the pairs the exam contrasts: EBS vs EFS vs S3
(block, file, object; single instance, many instances, anything); SQS vs
SNS vs EventBridge (queue, fan-out, rules); RDS vs DynamoDB (relational,
key-value; vertical, horizontal); CloudFront vs Global Accelerator (HTTP
caching, TCP/UDP anycast); NAT gateway vs NAT instance (managed, cheap and
yours to patch); Security group vs NACL (stateful instance, stateless
subnet). Learn the left column cold and the right column follows.
""",
                optional=True,
            ),
            video("Lambda, API Gateway and SQS together", "lambda-apigw-sqs", minutes=38),
        ),
    ),
)

_MERN_MODULES = (
    ModuleSpec(
        "JavaScript and Node.js",
        "Modern JavaScript, the event loop, and a first HTTP server.",
        (
            text(
                "The event loop and asynchronous code",
                "event-loop-async",
                """
# The event loop

JavaScript runs on one thread, and yet a Node server handles thousands of
connections at once. It manages this by never waiting: a call that would
block — reading a file, querying a database, waiting for a socket — is handed
to the runtime with a callback, and the thread moves on to the next event in
the queue. When the operation finishes, its callback is queued, and the event
loop runs it when the thread is free. CPU-heavy work is the one thing this
model punishes: a loop that takes two seconds stalls every other request for
two seconds.

Promises made callbacks composable, and `async`/`await` made promises read
like sequential code. `const rows = await db.query(sql)` pauses this function
only, not the thread. Always `await` inside `try`/`catch` or attach a
`.catch`; an unhandled rejection crashes the process in current Node.

`Promise.all` runs independent operations concurrently and waits for all of
them; use it whenever two awaits do not depend on each other, and the page
that took 600 ms takes 300.
""",
                preview=True,
            ),
            video(
                "Express: routing, middleware and errors", "express-routing-middleware", minutes=36
            ),
            document(
                "Lab: a REST API for course enquiries",
                "lab-enquiries-api",
                """
Build an Express API with routes to create, list, fetch and close an enquiry.
An enquiry has a name, phone, course of interest, source and status. Validate
the phone as ten digits, return 400 with a field-level error object when
validation fails, 404 for an unknown id, and a consistent JSON envelope on
every response. Add a logging middleware that prints method, path, status and
duration. Write the tests with supertest before the handlers, and make them
pass.
""",
            ),
        ),
    ),
    ModuleSpec(
        "MongoDB and Mongoose",
        "Documents, schemas, indexes and the aggregation pipeline.",
        (
            text(
                "Modelling data as documents",
                "modelling-documents",
                """
# Modelling data as documents

A relational schema normalises: a student, their enrolments and their
payments live in three tables joined by keys. A document database asks a
different question — what does the application read together? — and stores
that together. A student document might embed their current enrolments,
because the profile page always shows them, and reference payments by id,
because the ledger is long and read separately.

Embed when the child is small, bounded and read with the parent. Reference
when the child is large, unbounded, or shared between parents. A document
has a 16 MB ceiling, and a design that grows a document without limit —
appending every attendance record to the student — will hit it in a year.

Mongoose adds a schema on top so the shape is declared once, validated on
save, and typed in your editor. Indexes are declared in the schema too, and a
query that filters or sorts on an unindexed field of a large collection is
the most common performance problem in a first MERN project.
""",
            ),
            video("Aggregation pipeline by example", "aggregation-pipeline", minutes=33),
            link(
                "MongoDB manual: data modelling",
                "mongodb-data-modelling",
                f"{DOCS_HOST}/mongodb/manual/core/data-modeling-introduction",
            ),
        ),
    ),
    ModuleSpec(
        "React and the full stack",
        "Components, hooks, state, and wiring the front end to the API.",
        (
            text(
                "Components, props and state",
                "components-props-state",
                """
# Components, props and state

A React component is a function that takes props and returns what to render.
It runs again whenever its props or its state change, and React reconciles
the new output with the old to update only what differs in the DOM. This is
the whole model: describe the UI for a given state, and let React work out
the transitions.

`useState` gives a component memory between renders; `useEffect` runs code
after render for things outside React, such as fetching data or subscribing
to a socket. The dependency array of an effect is a promise about what the
effect reads; leave something out and you get stale values, put in something
that changes every render and you get a loop.

State lives at the lowest component that needs it and no lower. Two
siblings that must agree share state in their parent. When that parent is
the whole application, reach for context or a store — but not before, and
never for server data, which belongs in a query cache.
""",
                links=(("React reference: hooks", f"{DOCS_HOST}/react/reference/react/hooks"),),
            ),
            document(
                "Project brief: batch dashboard",
                "project-brief-batch-dashboard",
                """
Capstone brief. Build a dashboard for a training centre showing batches with
their trainer, seats filled, and the next class. Requirements: React with
React Router, data from your Express API, optimistic updates when marking a
seat, a loading and an error state for every fetch, and a responsive layout
that works on a phone. Deploy the API and the front end and submit both URLs
with the repository. Marking: functionality 40, code quality 30, UI 20,
deployment 10.
""",
                optional=True,
            ),
            video("Authentication with JWT end to end", "jwt-auth-end-to-end", minutes=41),
        ),
    ),
)

_DATA_SCIENCE_MODULES = (
    ModuleSpec(
        "Python for data",
        "NumPy, pandas and the habit of looking at the data before modelling it.",
        (
            text(
                "pandas DataFrames: the grammar of tabular data",
                "pandas-dataframes",
                """
# DataFrames

A DataFrame is a table with labelled rows and columns, and almost everything
you will do in this course is a transformation of one DataFrame into
another. `pd.read_csv` loads; `.head()`, `.info()` and `.describe()` are the
three calls to make before anything else, because they show the shape, the
types and the missing values, and most data problems are visible in them.

Selection reads like the question: `df[df["city"] == "Jaipur"]` filters
rows, `df[["name", "fee"]]` picks columns, `df.loc[rows, cols]` does both by
label and `.iloc` by position. `groupby` splits, applies and combines:
`df.groupby("course")["fee"].mean()` is the average fee per course in one
line. `merge` is a SQL join, `pivot_table` is a spreadsheet pivot, and
`melt` is its inverse.

Missing values propagate through arithmetic as NaN, and deciding what to do
about them — drop, fill, flag — is a modelling decision, not a cleaning
chore. Write down the decision in the notebook where you make it.
""",
                preview=True,
            ),
            video("NumPy arrays and vectorised thinking", "numpy-vectorised", minutes=28),
            document(
                "Exploratory analysis worksheet",
                "eda-worksheet",
                """
Using the enquiries dataset from the lab drive: report the number of rows and
columns, the share of missing values per column, the five most common
sources, the conversion rate by source and by city, the distribution of days
from enquiry to enrolment, and one chart per finding. End with three
questions the data cannot answer and what you would need to collect.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Machine learning with scikit-learn",
        "Supervised learning, model evaluation and the discipline of a held-out set.",
        (
            text(
                "Train, validate, test: why three sets",
                "train-validate-test",
                """
# Three sets

A model that scores 99 % on the data it was fitted to has learnt that data,
not the problem. The test set exists to be touched once, at the end, to
report how the model does on rows it has never seen. The validation set (or
cross-validation over the training set) is where you compare models and tune
hyper-parameters; every decision you make while looking at a set leaks a
little of it into the model.

`train_test_split` with a fixed `random_state` makes the split
reproducible; `stratify=y` keeps the class balance in each part.
`cross_val_score` averages over folds so a lucky split does not flatter a
model. The metric must match the question: accuracy misleads on imbalanced
classes, where precision, recall and the F1 score say what actually
happened.

A pipeline (`make_pipeline(StandardScaler(), LogisticRegression())`) fits
the scaler on the training folds only, which is the difference between an
honest score and a leaked one.
""",
            ),
            video("Linear and logistic regression", "linear-logistic-regression", minutes=39),
            link(
                "scikit-learn user guide",
                "sklearn-user-guide",
                f"{DOCS_HOST}/scikit-learn/stable/user_guide",
            ),
        ),
    ),
    ModuleSpec(
        "Capstone",
        "A modelling project on a real dataset, presented to the class.",
        (
            text(
                "Structuring a data science project",
                "structuring-a-project",
                """
# Structuring a project

Notebooks are for exploring and reports are for concluding; the code that
survives goes in a package. A working layout: `data/raw` never edited,
`data/processed` reproducible from raw by a script, `notebooks/` numbered in
the order they were written, `src/` with the feature and model code imported
by the notebooks, and a `README` that says how to run it all from a clean
clone.

Version the code and the environment, not the data; record the data's
source, date and checksum. A `Makefile` or a `dvc.yaml` that rebuilds
processed data and models from raw is the difference between a project and
a folder.

The report answers the question that was asked, states the model's
performance on the held-out set with its uncertainty, and lists what would
change the conclusion. A plot per claim, no plot without a claim.
""",
                links=(
                    (
                        "Cookiecutter data science",
                        f"{DOCS_HOST}/drivendata/cookiecutter-data-science",
                    ),
                ),
            ),
            document(
                "Capstone rubric",
                "capstone-rubric",
                """
Problem framing 15: the question is specific and the success metric agreed
before modelling. Data work 25: cleaning decisions recorded, leakage avoided,
features justified. Modelling 25: at least two model families compared with
cross-validation, hyper-parameters tuned on validation only. Evaluation 20:
held-out result with confidence interval, error analysis on the worst cases.
Communication 15: a ten-minute talk a counsellor could follow.
""",
                optional=True,
            ),
            video(
                "Presenting results to a non-technical audience", "presenting-results", minutes=22
            ),
        ),
    ),
)

_ETHICAL_HACKING_MODULES = (
    ModuleSpec(
        "Reconnaissance and scanning",
        "Finding what is exposed before anyone else does — lawfully, on the lab range.",
        (
            text(
                "Rules of engagement and the lab range",
                "rules-of-engagement",
                """
# Rules of engagement

Every technique in this course is exercised against the institute's lab
range — a private network of deliberately vulnerable machines — and nothing
else. Scanning a system you do not own or have written permission to test is
a crime under the IT Act, and the first lesson of professional testing is
that the scope document, signed by the client, is what separates a tester
from an attacker.

The range runs on the `10.99.0.0/16` network, reachable only from the lab
VPN. Each student has their own set of targets, so what you break does not
break a classmate's exercise, and the range is reset every night.

Take notes as you go: the target, the time, the command, the result. A
penetration test is a report, and a finding you cannot reproduce is a
finding the client cannot fix.
""",
                preview=True,
            ),
            video(
                "Nmap: host discovery to service versions", "nmap-discovery-versions", minutes=37
            ),
            document(
                "Lab: map the range",
                "lab-map-the-range",
                """
From the lab VPN, discover every live host in your assigned /24, identify
open ports and service versions, and produce a table of host, port, service,
version and one line on what the version suggests. Do not exploit anything
yet. Submit the table and the exact commands you used, with timing options
explained.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Web application attacks",
        "The OWASP Top 10 in practice on the range's deliberately broken web applications.",
        (
            text(
                "Injection: SQL, command and template",
                "injection-attacks",
                """
# Injection

Injection happens wherever user input is concatenated into something that
is then interpreted: a SQL query, a shell command, a template. The classic
`' OR 1=1 --` in a login form works because the application built
`WHERE user = '<input>'` by string joining, and the fix is the same in
every language — parameterised queries, where the input travels separately
from the code and is never parsed as it.

Find it by watching for the tell: an error page that quotes SQL, a delay
when you append `; sleep 5`, a template that renders `{{7*7}}` as 49. Confirm
it with the least harmful proof — reading the database version — and stop.
The report needs the evidence, not the data.

Blind injection, where nothing is echoed back, is answered one bit at a
time through timing or through true/false page differences; sqlmap
automates this and the module shows how to use it responsibly.
""",
            ),
            video("Burp Suite: intercept, repeat, intrude", "burp-suite-workflow", minutes=44),
            link(
                "OWASP Top 10",
                "owasp-top-10",
                f"{DOCS_HOST}/owasp/www-project-top-ten",
            ),
        ),
    ),
    ModuleSpec(
        "Reporting",
        "Writing a finding a developer can fix and a manager can prioritise.",
        (
            text(
                "Anatomy of a finding",
                "anatomy-of-a-finding",
                """
# Anatomy of a finding

A finding has a title that names the weakness and the asset, a severity
with the reasoning behind it, the affected component, steps to reproduce
that a developer can follow in five minutes, evidence (a request and
response, a screenshot), the impact in business terms, and a remediation
that says what to change, not just what is wrong.

Severity is impact times likelihood, and CVSS gives it a number, but the
number is the start of a conversation: an SQL injection on an internal
reporting tool used by two people is not the same risk as one on the
customer portal. Say which it is.

Write the executive summary last, in a page, for somebody who will read
nothing else: what was tested, what was found, what to fix first.
""",
                links=(("CVSS 3.1 calculator", f"{DOCS_HOST}/first/cvss/calculator/3.1"),),
            ),
            document(
                "Report template",
                "report-template",
                """
Cover page; scope and rules of engagement; executive summary; methodology;
findings by severity with the fields from the lesson; appendix of tools and
versions; appendix of raw evidence. Use the institute's template on the lab
drive and submit as PDF.
""",
                optional=True,
            ),
            video("Presenting a report to a client", "presenting-a-report", minutes=20),
        ),
    ),
)

_CCNA_MODULES = (
    ModuleSpec(
        "Network fundamentals",
        "The OSI model, IPv4 addressing and subnetting by hand.",
        (
            text(
                "Subnetting without a calculator",
                "subnetting-by-hand",
                """
# Subnetting

An IPv4 address is 32 bits; the mask says how many of them name the
network. `/24` leaves 8 host bits and 254 usable hosts; every bit borrowed
halves the hosts and doubles the subnets. The block size in the interesting
octet is 256 minus the mask value there: a `/26` has mask 255.255.255.192,
block size 64, subnets at .0, .64, .128 and .192, each with 62 hosts.

To find the network of any address, find the multiple of the block size
at or below it. 192.168.10.77/26 sits in the .64 block; its broadcast is
.127; usable hosts .65 to .126. Practise until this takes ten seconds,
because the exam gives about a minute a question.

VLSM assigns different masks to different subnets so a point-to-point link
takes a /30 and a floor takes a /24, and the addressing plan is the first
thing a network engineer writes down.
""",
                preview=True,
            ),
            video("Switching: VLANs and trunks", "vlans-and-trunks", minutes=35),
            document(
                "Subnetting practice sheet",
                "subnetting-practice-sheet",
                """
Fifty subnetting problems in four sets: given address and mask find network,
broadcast and usable range; given a network and a host count find the
smallest mask; given a block and a list of departments produce a VLSM plan;
and ten reverse problems from a routing table. Answers on the last page —
do the sheet first.
""",
            ),
        ),
    ),
    ModuleSpec(
        "Routing",
        "Static routes, OSPF, and reading a routing table.",
        (
            text(
                "How a router chooses a route",
                "how-a-router-chooses",
                """
# Choosing a route

A router forwards each packet to the most specific matching route — the
longest prefix — in its routing table. When two routes to the same prefix
come from different sources, administrative distance decides: connected 0,
static 1, OSPF 110, RIP 120. Within one protocol, the metric decides. This
three-level rule explains almost every "why did it go that way?" in the
lab.

`show ip route` prints the table with a letter per source; read the
codes line at the top. A static route is one line — `ip route 10.2.0.0
255.255.0.0 10.1.1.2` — and a default route is the same with all zeros.
OSPF learns routes by exchanging link-state advertisements, builds the
same map on every router, and computes the shortest path with Dijkstra.

Enable it with `router ospf 1` and `network 10.1.0.0 0.0.255.255 area 0`,
check neighbours with `show ip ospf neighbor`, and remember the wildcard
mask is the inverse of the subnet mask.
""",
            ),
            video("OSPF single area lab", "ospf-single-area-lab", minutes=40),
            link(
                "Cisco CCNA exam topics",
                "ccna-exam-topics",
                f"{DOCS_HOST}/cisco/ccna/200-301-exam-topics",
            ),
        ),
    ),
    ModuleSpec(
        "Services and security",
        "DHCP, NAT, ACLs and the basics of keeping a network honest.",
        (
            text(
                "Access control lists",
                "access-control-lists",
                """
# Access control lists

An ACL is an ordered list of permit and deny statements matched top to
bottom, with an implicit deny at the end. A standard ACL matches source
address only and is placed close to the destination; an extended ACL
matches source, destination, protocol and port and is placed close to the
source, so unwanted traffic is dropped before it crosses the network.

Write the specific lines before the general ones, because the first match
wins; a `permit ip any any` on line one makes every later line dead.
Apply the list to an interface with a direction — `ip access-group 110 in`
— and remember an ACL that is written but not applied does nothing.

`show access-lists` counts matches per line, which is how you find out
whether the rule you wrote is the one the traffic hits.
""",
                links=(("ACL configuration guide", f"{DOCS_HOST}/cisco/ios/security/acl"),),
            ),
            document(
                "NAT and DHCP lab",
                "nat-dhcp-lab",
                """
Configure the branch router as a DHCP server for VLAN 10 with a two-day
lease and the site's DNS, exclude the first ten addresses, then configure
PAT so the whole branch leaves through the single public address on Gi0/0.
Verify with show ip nat translations while a host browses, and with show ip
dhcp binding.
""",
                optional=True,
            ),
            video("Troubleshooting from the bottom up", "troubleshooting-bottom-up", minutes=27),
        ),
    ),
)


COURSES: list[CourseSpec] = [
    CourseSpec(
        slug="rhcsa",
        title="RHCSA — Red Hat Certified System Administrator (EX200)",
        category="linux-devops",
        difficulty=CourseDifficulty.INTERMEDIATE,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("25000.00"),
        minutes=60 * 80,
        short="Hands-on preparation for the EX200 performance exam on RHEL 9, lab by lab.",
        description=(
            "Grras's flagship Linux course. Eighty hours of lab work on Red Hat Enterprise "
            "Linux 9 covering every published EX200 objective: the shell, users and "
            "permissions, storage with LVM, SELinux, firewalld, systemd, networking and "
            "rootless containers with podman. Every session ends at the keyboard, and the "
            "final week is two full mock exams under exam conditions."
        ),
        objectives=(
            "Administer users, groups, permissions and sudo on a RHEL 9 system",
            "Create and grow LVM storage and mount it persistently",
            "Run services under SELinux enforcing and firewalld without switching either off",
            "Manage systemd units, boot targets and recover a lost root password",
            "Run a rootless container as a persistent systemd user service",
        ),
        prerequisites=("Comfortable using a computer; no prior Linux required",),
        status=PublishStatus.PUBLISHED,
        authors=(("trainer", CourseAuthorRole.OWNER),),
        modules=_RHCSA_MODULES,
    ),
    CourseSpec(
        slug="devops-engineering",
        title="DevOps Engineering with Docker, Kubernetes & Ansible",
        category="linux-devops",
        difficulty=CourseDifficulty.ADVANCED,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("45000.00"),
        minutes=60 * 120,
        short="Containers, orchestration, configuration management and CI/CD on a real cluster.",
        description=(
            "For people who already administer Linux and want to run software the way "
            "modern teams do. Docker from the kernel up, a three-node Kubernetes cluster "
            "per pair of students, Ansible for the machines beneath it, and a GitLab "
            "pipeline that builds, scans and deploys on every push. The final project "
            "takes a service from a repository to a monitored production deployment."
        ),
        objectives=(
            "Build small, cacheable, multi-stage container images",
            "Deploy, scale, roll out and roll back workloads on Kubernetes",
            "Write idempotent Ansible playbooks and roles",
            "Design and run a CI/CD pipeline with tests, scans and environments",
        ),
        prerequisites=("RHCSA or equivalent Linux administration", "Basic Git"),
        status=PublishStatus.PUBLISHED,
        authors=(("trainer", CourseAuthorRole.OWNER), ("shivani.nair", CourseAuthorRole.EDITOR)),
        modules=_DEVOPS_MODULES,
    ),
    CourseSpec(
        slug="python-django-full-stack",
        title="Python & Django Full Stack Development",
        category="programming",
        difficulty=CourseDifficulty.BEGINNER,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("35000.00"),
        minutes=60 * 100,
        short="From a first print statement to a deployed Django application with a REST API.",
        description=(
            "Python from the beginning, taught through programs rather than slides, then "
            "Django: models, the ORM, views, templates, forms, authentication, the admin, "
            "Django REST Framework and deployment to a Linux server. The running example "
            "is a student portal, built feature by feature across the course, and every "
            "student leaves with it deployed under their own name."
        ),
        objectives=(
            "Write idiomatic Python using the standard library and virtual environments",
            "Model a domain in Django and query it with the ORM",
            "Build and secure a REST API with Django REST Framework",
            "Deploy a Django project with gunicorn, nginx and HTTPS",
        ),
        prerequisites=(),
        status=PublishStatus.PUBLISHED,
        authors=(("neha.saxena", CourseAuthorRole.OWNER),),
        modules=_PYTHON_MODULES,
    ),
    CourseSpec(
        slug="aws-solutions-architect",
        title="AWS Certified Solutions Architect — Associate (SAA-C03)",
        category="cloud",
        difficulty=CourseDifficulty.INTERMEDIATE,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("32000.00"),
        minutes=60 * 60,
        short="The SAA-C03 syllabus built in a real account, with the exam technique to pass it.",
        description=(
            "Every service on the SAA-C03 exam guide, built rather than described: VPCs, "
            "EC2, S3, IAM, RDS, DynamoDB, Lambda, SQS, CloudFront and the rest, in an "
            "account each student keeps. The second half of the course is architecture: "
            "reading scenario questions, the Well-Architected pillars, and four full "
            "practice exams with every answer explained."
        ),
        objectives=(
            "Design a multi-AZ VPC with public and private tiers",
            "Apply IAM least privilege with roles rather than keys",
            "Choose between storage, database and messaging services for a scenario",
            "Pass SAA-C03",
        ),
        prerequisites=("Basic networking and Linux",),
        status=PublishStatus.PUBLISHED,
        authors=(
            ("rohit.kumawat", CourseAuthorRole.OWNER),
            ("shivani.nair", CourseAuthorRole.EDITOR),
        ),
        modules=_AWS_MODULES,
    ),
    CourseSpec(
        slug="mern-full-stack",
        title="MERN Full Stack Web Development",
        category="programming",
        difficulty=CourseDifficulty.INTERMEDIATE,
        visibility=CourseVisibility.INTERNAL,
        fee=Decimal("38000.00"),
        minutes=60 * 110,
        short="MongoDB, Express, React and Node: one language from database to browser.",
        description=(
            "JavaScript end to end. Modern JavaScript and Node's event loop, Express APIs "
            "with proper validation and tests, MongoDB modelled as documents rather than "
            "tables, and React with hooks and a router. The capstone is a deployed batch "
            "dashboard for a training centre. Internal visibility: offered to enrolled "
            "Pune students and corporate cohorts, not listed publicly."
        ),
        objectives=(
            "Write asynchronous JavaScript that does not block the event loop",
            "Build, validate and test an Express REST API",
            "Model and index data in MongoDB with Mongoose",
            "Build a React front end with hooks, routing and authentication",
        ),
        prerequisites=("HTML and CSS", "Any programming language"),
        status=PublishStatus.PUBLISHED,
        authors=(("ankit.kulkarni", CourseAuthorRole.OWNER),),
        modules=_MERN_MODULES,
    ),
    CourseSpec(
        slug="data-science-ml",
        title="Data Science & Machine Learning with Python",
        category="data-science",
        difficulty=CourseDifficulty.ADVANCED,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("65000.00"),
        minutes=60 * 150,
        short="pandas, statistics and scikit-learn, ending in a capstone on a real dataset.",
        description=(
            "A modelling course, not a tooling course. NumPy and pandas for data work, "
            "enough statistics to know what a result means, scikit-learn for supervised "
            "and unsupervised learning, and a capstone project on a dataset of the "
            "student's choosing presented to the class. Submitted for review by the "
            "course author ahead of the winter intake."
        ),
        objectives=(
            "Explore and clean tabular data with pandas",
            "Fit, tune and honestly evaluate supervised models",
            "Structure a data science project so it can be reproduced",
            "Present a modelling result to a non-technical audience",
        ),
        prerequisites=("Python basics", "School-level mathematics"),
        status=PublishStatus.IN_REVIEW,
        authors=(("priya.malhotra", CourseAuthorRole.EDITOR),),
        modules=_DATA_SCIENCE_MODULES,
    ),
    CourseSpec(
        slug="ethical-hacking",
        title="Ethical Hacking & Penetration Testing",
        category="cyber-security",
        difficulty=CourseDifficulty.INTERMEDIATE,
        visibility=CourseVisibility.PRIVATE,
        fee=Decimal("42000.00"),
        minutes=60 * 90,
        short="Reconnaissance, web application attacks and reporting, on a private lab range.",
        description=(
            "Offensive security taught lawfully: every exercise runs against the "
            "institute's own vulnerable range over VPN. Nmap, Burp Suite, the OWASP Top "
            "10 in practice, and — the part most courses skip — writing a finding a "
            "developer can fix. Still in draft while the range is rebuilt; private until "
            "the legal agreement for students is finalised."
        ),
        objectives=(
            "Scope and document a test under rules of engagement",
            "Discover hosts and services and identify likely weaknesses",
            "Find and prove injection and authentication flaws in a web application",
            "Write a penetration test report with prioritised findings",
        ),
        prerequisites=("Linux and networking fundamentals",),
        status=PublishStatus.DRAFT,
        authors=(("sameer.bhatt", CourseAuthorRole.OWNER),),
        modules=_ETHICAL_HACKING_MODULES,
    ),
    CourseSpec(
        slug="ccna",
        title="CCNA 200-301 — Cisco Certified Network Associate",
        category="networking",
        difficulty=CourseDifficulty.BEGINNER,
        visibility=CourseVisibility.PUBLIC,
        fee=Decimal("18000.00"),
        minutes=60 * 70,
        short="Subnetting, switching, routing and security for the 200-301 exam.",
        description=(
            "Network fundamentals through to OSPF, ACLs and NAT on Cisco IOS, with a "
            "physical rack and Packet Tracer. Archived: the networking trainer has left "
            "and the course is not being offered to new batches until a replacement is "
            "hired. Past enrolments keep access to the material."
        ),
        objectives=(
            "Subnet IPv4 networks by hand and plan VLSM addressing",
            "Configure VLANs, trunks and inter-VLAN routing",
            "Configure static routing and single-area OSPF",
            "Secure a network with ACLs, DHCP snooping and port security",
        ),
        prerequisites=(),
        status=PublishStatus.ARCHIVED,
        authors=(("deepak.purohit", CourseAuthorRole.OWNER),),
        modules=_CCNA_MODULES,
    ),
]


# ---------------------------------------------------------------------------
# The imported SITP tracks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    """What one SITP track is about, enough to write its three lessons."""

    subject: str
    weeks: tuple[str, ...]
    tools: tuple[str, ...]
    project: str


#: Matched against the lower-cased course title, first hit wins, so the more
#: specific keys come before the general ones — and a key is never a fragment
#: another title contains ("soc" is inside "associate").
_TRACKS: list[tuple[str, Track]] = [
    (
        "agentic ai",
        Track(
            "agentic AI systems",
            (
                "Python refresher and prompt engineering",
                "Large language model APIs and structured output",
                "Tool calling and function schemas",
                "Retrieval-augmented generation with a vector store",
                "Multi-step agents, planning and memory",
                "Evaluation, guardrails and cost control",
            ),
            ("Python 3.12", "the OpenAI-compatible API", "LangChain", "Chroma", "Streamlit"),
            "an agent that answers questions about a college's own documents and books a meeting",
        ),
    ),
    (
        "cloud computing",
        Track(
            "cloud computing with AI services",
            (
                "Linux and networking fundamentals",
                "Virtual machines, storage and IAM",
                "Serverless functions and managed databases",
                "Containers and a managed Kubernetes cluster",
                "Managed AI services: vision, speech and language APIs",
                "Cost, monitoring and a production checklist",
            ),
            ("AWS", "the AWS CLI", "Docker", "Terraform", "CloudWatch"),
            "a document-classification service deployed serverlessly with a monitored budget",
        ),
    ),
    (
        "cyber security with ai",
        Track(
            "cyber security with AI-assisted analysis",
            (
                "Networking, Linux and the attacker's view",
                "Reconnaissance and vulnerability scanning",
                "Web application security and the OWASP Top 10",
                "Log analysis and anomaly detection with Python",
                "Using language models to triage alerts and write reports",
                "Incident response tabletop and reporting",
            ),
            ("Kali Linux", "Nmap", "Burp Suite", "Wazuh", "pandas"),
            "an alert-triage assistant over a week of SIEM logs, with a written incident report",
        ),
    ),
    (
        "soc cyber",
        Track(
            "security operations centre work",
            (
                "Networking and Windows/Linux logging",
                "SIEM fundamentals and log onboarding",
                "Detection rules and the MITRE ATT&CK matrix",
                "Alert triage, escalation and ticketing",
                "Threat intelligence and phishing analysis",
                "Incident handling and shift handover",
            ),
            ("Wazuh", "Splunk Free", "Sysmon", "Wireshark", "TheHive"),
            "a full shift on the lab SOC: onboarding, detection, triage and a handover report",
        ),
    ),
    (
        "data analytics",
        Track(
            "data analytics with AI tooling",
            (
                "Excel and SQL for analysis",
                "Python and pandas",
                "Descriptive statistics and visualisation",
                "Dashboards in Power BI",
                "AI-assisted analysis and narrative reporting",
                "Capstone: a business question answered end to end",
            ),
            ("PostgreSQL", "pandas", "Power BI Desktop", "Jupyter", "matplotlib"),
            "a sales-performance dashboard with a written analysis of one retail dataset",
        ),
    ),
    (
        "data science",
        Track(
            "data science with machine learning",
            (
                "Python, NumPy and pandas",
                "Statistics for data science",
                "Supervised learning with scikit-learn",
                "Unsupervised learning and feature engineering",
                "Neural networks with PyTorch",
                "Capstone modelling project",
            ),
            ("Jupyter", "pandas", "scikit-learn", "PyTorch", "MLflow"),
            "a predictive model on a public dataset with a reproducible pipeline and a report",
        ),
    ),
    (
        "mern",
        Track(
            "full-stack web development with MERN",
            (
                "HTML, CSS and modern JavaScript",
                "Node.js and Express APIs",
                "MongoDB and Mongoose",
                "React: components, hooks and routing",
                "Authentication and deployment",
                "Capstone application",
            ),
            ("Node.js 20", "Express", "MongoDB Atlas", "React 18", "Vercel"),
            "a deployed MERN application with authentication and a documented API",
        ),
    ),
    (
        "data engineer",
        Track(
            "data engineering on AWS",
            (
                "SQL and data modelling",
                "Python for pipelines",
                "S3, Glue and the data catalogue",
                "Athena, Redshift and query design",
                "Orchestration with Step Functions and Airflow",
                "Streaming with Kinesis",
            ),
            ("AWS Glue", "Athena", "Redshift", "Apache Airflow", "PySpark"),
            "a batch and streaming pipeline from raw events to a queryable warehouse",
        ),
    ),
    (
        "ml engineer",
        Track(
            "machine learning engineering on AWS",
            (
                "Python and scikit-learn refresher",
                "SageMaker notebooks and training jobs",
                "Feature stores and data preparation",
                "Model deployment as endpoints",
                "Monitoring, drift and retraining",
                "MLOps with pipelines",
            ),
            ("SageMaker", "boto3", "scikit-learn", "Docker", "CodePipeline"),
            "a trained, deployed and monitored model behind an API with an automated retrain",
        ),
    ),
    (
        "solution architect",
        Track(
            "AWS solutions architecture",
            (
                "Global infrastructure, IAM and the VPC",
                "Compute: EC2, Lambda and containers",
                "Storage and databases",
                "Networking, delivery and DNS",
                "Resilience, decoupling and messaging",
                "Cost optimisation and exam technique",
            ),
            ("the AWS console", "the AWS CLI", "CloudFormation", "CloudWatch", "Cost Explorer"),
            "a three-tier, multi-AZ architecture built from a written requirement and costed",
        ),
    ),
    (
        "az 204",
        Track(
            "Azure development (AZ-204)",
            (
                "Azure fundamentals and the CLI",
                "App Service and Azure Functions",
                "Cosmos DB and Azure Storage",
                "Identity with Entra ID and Key Vault",
                "Messaging with Service Bus and Event Grid",
                "Monitoring, caching and CDN",
            ),
            (
                "the Azure CLI",
                "Visual Studio Code",
                ".NET 8",
                "Azure Functions Core Tools",
                "Bicep",
            ),
            "an event-driven application on App Service, Functions and Cosmos DB",
        ),
    ),
    (
        "pl300",
        Track(
            "Power BI data analysis (PL-300)",
            (
                "Getting and transforming data with Power Query",
                "Data modelling and relationships",
                "DAX measures and calculated columns",
                "Visuals, reports and accessibility",
                "Row-level security and deployment",
                "Exam preparation",
            ),
            ("Power BI Desktop", "the Power BI service", "DAX Studio", "Excel", "SQL Server"),
            "a published report over a multi-table model with row-level security",
        ),
    ),
    (
        "python pro",
        Track(
            "professional Python programming",
            (
                "Syntax, data structures and functions",
                "Object-oriented Python and typing",
                "The standard library and packaging",
                "Testing with pytest",
                "Working with files, APIs and databases",
                "A command-line project from scratch",
            ),
            ("Python 3.12", "pytest", "ruff", "SQLite", "requests"),
            "a packaged, tested command-line tool published to a private index",
        ),
    ),
]

#: Groups A-D are the foundation cohorts: the same programme for everyone
#: before they choose a track.
_FOUNDATION = Track(
    "the industry-readiness foundation programme",
    (
        "Linux, the shell and Git",
        "Programming fundamentals in Python",
        "Databases and SQL",
        "Web fundamentals: HTTP, HTML and APIs",
        "Cloud basics and deployment",
        "Aptitude, communication and interview practice",
    ),
    ("Ubuntu 24.04", "Git", "Python 3.12", "PostgreSQL", "Visual Studio Code"),
    "a small web application built, versioned and deployed by a team of three",
)


def track_for(title: str) -> Track:
    lowered = title.lower()
    for key, track in _TRACKS:
        if key in lowered:
            return track
    return _FOUNDATION


def sitp_lessons(title: str) -> list[LessonSpec]:
    """The three text lessons an imported track receives, written for it."""
    track = track_for(title)
    weeks = "\n".join(f"{n}. **Week {n}** — {topic}" for n, topic in enumerate(track.weeks, 1))
    tools = ", ".join(track.tools[:-1]) + f" and {track.tools[-1]}"
    syllabus = f"""
# Syllabus overview

This SITP track is a six-week, full-time programme in {track.subject}, run for
college cohorts under the Summer Industrial Training Programme. Each week has
four days of instructor-led sessions in the morning, lab time in the
afternoon, and a Friday review where the week's work is demonstrated.

{weeks}

The programme ends with a project — {track.project} — presented to the
trainers and to a panel from the placement cell. Attendance below the
institute's threshold, or an unsubmitted project, means no completion
certificate, whatever the test scores.
"""
    lab = f"""
# Lab guide

Every lab in this track uses {tools}. Accounts and lab machines are issued on
day one; keep the credentials sheet, because the lab environment is reset
between cohorts and cannot be recovered from a previous batch.

Labs are done individually unless the sheet says otherwise, and each lab
sheet states what to submit: usually a short write-up, the commands or code
used, and a screenshot of the result. Submit through the lesson's assignment
before the Friday review — late submissions are accepted for a week with a
note, and not after that.

When a lab does not work, the order is: read the error, check the lab sheet's
troubleshooting section, ask the person next to you, then ask the trainer. A
problem you solved yourself is one you will remember in the interview.
"""
    assessment = f"""
# Assessment guide

Marks for this track come from four places. Weekly tests (30 %): a short
online test every Friday on that week's material, best five of six count.
Lab work (20 %): each lab sheet is marked complete or incomplete, and the
share completed is the mark. Project (40 %): {track.project}, marked on
working software, code quality, and the presentation. Viva (10 %): a
ten-minute conversation with a trainer about what you built and why.

The pass mark is the institute's standard, and the completion certificate
also requires the attendance threshold. Marks are published in the portal
within a week of the final presentation, and a student may ask for a review
of any mark within seven days of publication.
"""
    return [
        text("Syllabus overview", "syllabus-overview", syllabus, minutes=20, preview=True),
        text("Lab guide", "lab-guide", lab, minutes=15),
        text("Assessment guide", "assessment-guide", assessment, minutes=15),
    ]


# ---------------------------------------------------------------------------
# The question bank
# ---------------------------------------------------------------------------

MCQ, MULTI, TF, SA, LA = (
    QuestionType.MCQ,
    QuestionType.MULTIPLE,
    QuestionType.TRUE_FALSE,
    QuestionType.SHORT_ANSWER,
    QuestionType.LONG_ANSWER,
)
E, M, H = Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD

#: A question is ``(type, difficulty, text, answer, tags[, explanation])``.
#: For MCQ and multiple, ``answer`` is the option list with the correct ones
#: marked by a leading ``*``; for true/false it is the truth; for short answer
#: it is the accepted answers; for long answer it is ``None``.
Item = tuple

QUESTIONS: dict[str, list[Item]] = {
    "rhcsa": [
        (
            MCQ,
            E,
            "Which command shows the current working directory?",
            ["*pwd", "ls", "cd", "dir"],
            ["shell", "basics"],
        ),
        (
            MCQ,
            E,
            "Which directory holds system configuration files on a Red Hat system?",
            ["/var", "*/etc", "/usr", "/opt"],
            ["filesystem"],
        ),
        (
            MCQ,
            E,
            "What does the # at the end of a shell prompt indicate?",
            [
                "A comment follows",
                "*The shell is running as root",
                "The command failed",
                "A job is in the background",
            ],
            ["shell"],
        ),
        (
            MCQ,
            E,
            "Which command creates a new user account?",
            ["adduser-new", "*useradd", "mkuser", "newuser"],
            ["users"],
        ),
        (
            MCQ,
            M,
            "Which command lists logical volumes?",
            ["pvs", "vgs", "*lvs", "fdisk -l"],
            ["lvm", "storage"],
        ),
        (
            MCQ,
            M,
            "After lvextend on an XFS volume, which command makes the extra space usable?",
            ["resize2fs", "*xfs_growfs", "mkfs.xfs", "mount -o remount"],
            ["lvm", "xfs"],
        ),
        (
            MCQ,
            M,
            "Which file is read at boot to mount file systems persistently?",
            ["/etc/mtab", "/proc/mounts", "*/etc/fstab", "/etc/mounts.conf"],
            ["storage", "fstab"],
        ),
        (
            MCQ,
            M,
            "Which command restores the SELinux context the policy expects on a path?",
            ["chcon -R", "*restorecon -Rv", "setenforce 1", "semanage relabel"],
            ["selinux"],
        ),
        (
            MCQ,
            H,
            "A web page under /srv/web returns 403 while permissions are 644 and SELinux is "
            "enforcing. What is the most likely cause?",
            [
                "httpd is not running",
                "*The files carry the wrong SELinux context",
                "The firewall blocks port 80",
                "The page is not index.html",
            ],
            ["selinux", "httpd"],
            "Files created outside /var/www keep the label of where they were made; restorecon "
            "after semanage fcontext fixes it.",
        ),
        (
            MCQ,
            H,
            "Which setting on a directory makes new files inherit the directory's group?",
            ["The sticky bit", "*The setgid bit", "The setuid bit", "Mode 777"],
            ["permissions"],
        ),
        (
            MCQ,
            H,
            "Which command lets a rootless podman container keep running after the user logs out?",
            [
                "systemctl enable --now podman",
                "*loginctl enable-linger user",
                "podman run --restart=always",
                "nohup podman start",
            ],
            ["containers", "podman"],
        ),
        (
            MCQ,
            H,
            "Which firewalld command opens the http service permanently in the default zone?",
            [
                "firewall-cmd --add-port=80",
                "*firewall-cmd --permanent --add-service=http && firewall-cmd --reload",
                "iptables -A INPUT -p tcp --dport 80 -j ACCEPT",
                "firewall-cmd --zone=public --enable http",
            ],
            ["firewalld"],
        ),
        (
            TF,
            E,
            "In Linux, a second disk is mounted into the single directory tree rather than "
            "appearing as a separate drive letter.",
            True,
            ["filesystem"],
        ),
        (
            TF,
            M,
            "Setting SELinux to permissive is an acceptable way to complete an EX200 task.",
            False,
            ["selinux", "exam"],
        ),
        (
            TF,
            M,
            "A volume group can be extended with a new physical volume while its logical volumes "
            "are mounted.",
            True,
            ["lvm"],
        ),
        (
            TF,
            H,
            "The setuid bit on a shell script is honoured by the Linux kernel.",
            False,
            ["permissions", "security"],
        ),
        (SA, E, "Which command shows the manual page for a command?", ["man"], ["shell"]),
        (
            SA,
            M,
            "Which command initialises a disk or partition as an LVM physical volume?",
            ["pvcreate"],
            ["lvm"],
        ),
        (
            SA,
            H,
            "Which command searches the audit log for recent SELinux denials (name the command "
            "only)?",
            ["ausearch"],
            ["selinux"],
        ),
        (
            LA,
            M,
            "Explain the three LVM objects and the order in which they are created, naming the "
            "command for each.",
            None,
            ["lvm"],
        ),
        (
            LA,
            H,
            "A service is running but clients cannot reach it. Describe, in order, how you would "
            "rule out the firewall, SELinux and the service's own binding, with the command you "
            "would use for each.",
            None,
            ["troubleshooting", "selinux", "firewalld"],
        ),
        (
            MULTI,
            M,
            "Which of the following are systemd boot targets?",
            ["*multi-user.target", "*graphical.target", "runlevel-3.target", "*rescue.target"],
            ["systemd"],
        ),
        (
            MULTI,
            H,
            "Which statements about /etc/fstab are true?",
            [
                "*A UUID may be used in place of a device path",
                "*A wrong entry can stop the system booting",
                "It is re-read automatically when edited",
                "*mount -a mounts every entry not yet mounted",
            ],
            ["fstab", "storage"],
        ),
    ],
    "devops-engineering": [
        (
            MCQ,
            E,
            "Which file defines how a Docker image is built?",
            ["docker-compose.yml", "*Dockerfile", "image.yaml", "Makefile"],
            ["docker"],
        ),
        (
            MCQ,
            E,
            "What is a container, most precisely?",
            [
                "A lightweight virtual machine",
                "*An isolated process on the host kernel",
                "A compressed image",
                "A hypervisor",
            ],
            ["docker", "concepts"],
        ),
        (
            MCQ,
            E,
            "Which Kubernetes object keeps a set number of pod replicas running?",
            ["Service", "*Deployment", "ConfigMap", "Ingress"],
            ["kubernetes"],
        ),
        (
            MCQ,
            E,
            "What language are Ansible playbooks written in?",
            ["JSON", "*YAML", "Python", "INI"],
            ["ansible"],
        ),
        (
            MCQ,
            M,
            "Why should COPY . . come after pip install in a Dockerfile?",
            [
                "Docker requires it",
                "*So a code change does not invalidate the dependency layer cache",
                "pip cannot see the code otherwise",
                "It reduces the image's layer count",
            ],
            ["docker", "dockerfile"],
        ),
        (
            MCQ,
            M,
            "Which Kubernetes Service type is reachable only inside the cluster?",
            ["NodePort", "LoadBalancer", "*ClusterIP", "ExternalName"],
            ["kubernetes", "networking"],
        ),
        (
            MCQ,
            M,
            "In Ansible, when does a handler run?",
            [
                "Before every task",
                "*Once at the end of the play, if a task notified it",
                "Every time it is notified",
                "Only with --force-handlers",
            ],
            ["ansible"],
        ),
        (
            MCQ,
            M,
            "Which command shows the rollout history of a Deployment?",
            [
                "kubectl get history",
                "*kubectl rollout history deployment/web",
                "kubectl describe rollout web",
                "kubectl logs deployment/web",
            ],
            ["kubernetes"],
        ),
        (
            MCQ,
            H,
            "A Pod is stuck in Pending. Which is the most likely reason?",
            [
                "The image has a bug",
                "*No node has the resources or tolerations the Pod needs",
                "The Service selector is wrong",
                "The container exited",
            ],
            ["kubernetes", "troubleshooting"],
            "Pending means unscheduled; scheduling fails on resources, taints, affinity or a "
            "missing PersistentVolume.",
        ),
        (
            MCQ,
            H,
            "Which Ansible variable source has the highest precedence?",
            ["group_vars/all", "host_vars", "role defaults", "*extra vars passed with -e"],
            ["ansible"],
        ),
        (
            MCQ,
            H,
            "In a multi-stage Dockerfile, what does COPY --from=build do?",
            [
                "Copies from the host's build directory",
                "*Copies files from an earlier stage named build",
                "Copies from the build cache",
                "Copies the Dockerfile",
            ],
            ["docker", "dockerfile"],
        ),
        (
            MCQ,
            H,
            "Which kernel feature limits how much CPU and memory a container may use?",
            ["Namespaces", "*cgroups", "seccomp", "AppArmor"],
            ["docker", "kernel"],
        ),
        (
            TF,
            E,
            "Data written inside a running container's file system survives docker rm by default.",
            False,
            ["docker", "volumes"],
        ),
        (
            TF,
            M,
            "An idempotent playbook reports no changes on its second run against an unchanged "
            "host.",
            True,
            ["ansible"],
        ),
        (TF, M, "A Kubernetes Service selects Pods by their IP addresses.", False, ["kubernetes"]),
        (
            TF,
            H,
            "Killing a Pod that belongs to a Deployment reduces the Deployment's replica count by "
            "one.",
            False,
            ["kubernetes"],
        ),
        (
            SA,
            E,
            "Which command builds an image from the Dockerfile in the current directory (give the "
            "two-word command)?",
            ["docker build", "docker build ."],
            ["docker"],
        ),
        (
            SA,
            M,
            "Which kubectl subcommand applies a manifest file?",
            ["apply", "kubectl apply"],
            ["kubernetes"],
        ),
        (
            SA,
            H,
            "Which Ansible command creates the directory skeleton of a new role?",
            ["ansible-galaxy init", "ansible-galaxy role init"],
            ["ansible"],
        ),
        (
            LA,
            M,
            "Describe the Kubernetes control loop and explain why deleting a Pod does not reduce "
            "the number of running replicas.",
            None,
            ["kubernetes"],
        ),
        (
            LA,
            H,
            "Design a five-stage CI/CD pipeline for a web service. For each stage state its "
            "trigger, what it produces and what makes it fail.",
            None,
            ["cicd"],
        ),
        (
            MULTI,
            M,
            "Which of these are valid Docker instructions?",
            ["*FROM", "*RUN", "INSTALL", "*ENTRYPOINT"],
            ["docker", "dockerfile"],
        ),
        (
            MULTI,
            H,
            "Which of the following are true of Kubernetes namespaces?",
            [
                "*They scope names of most objects",
                "*Resource quotas can be applied per namespace",
                "Nodes belong to a namespace",
                "*A Service in one namespace can be reached by DNS from another",
            ],
            ["kubernetes"],
        ),
    ],
    "python-django-full-stack": [
        (
            MCQ,
            E,
            "Which of these is the correct way to print in Python 3?",
            ['print "hello"', '*print("hello")', 'echo "hello"', "console.log('hello')"],
            ["python", "basics"],
        ),
        (
            MCQ,
            E,
            "Which data type is immutable?",
            ["list", "dict", "*tuple", "set"],
            ["python", "collections"],
        ),
        (
            MCQ,
            E,
            "What does len([1, 2, 3]) return?",
            ["2", "*3", "4", "An error"],
            ["python", "basics"],
        ),
        (
            MCQ,
            E,
            "Which file in a Django project maps URLs to views?",
            ["views.py", "*urls.py", "routes.py", "settings.py"],
            ["django"],
        ),
        (
            MCQ,
            M,
            'What does f"{fee:,.2f}" do to the number 25000?',
            ["Prints 25000", "*Prints 25,000.00", "Rounds to 25000.0", "Raises a ValueError"],
            ["python", "strings"],
        ),
        (
            MCQ,
            M,
            "Which command creates migration files from model changes?",
            [
                "manage.py migrate",
                "*manage.py makemigrations",
                "manage.py syncdb",
                "manage.py createmigration",
            ],
            ["django", "orm"],
        ),
        (
            MCQ,
            M,
            "In Django, what is a QuerySet?",
            [
                "A list of dictionaries",
                "*A lazy description of a database query",
                "A cached table",
                "A raw SQL string",
            ],
            ["django", "orm"],
        ),
        (
            MCQ,
            M,
            "Which DRF class generates a serializer from a model's fields?",
            ["Serializer", "*ModelSerializer", "AutoSerializer", "FieldSerializer"],
            ["drf"],
        ),
        (
            MCQ,
            H,
            "Student.objects.filter(city='Jaipur').count() runs how many queries?",
            ["Zero", "*One", "Two", "One per row"],
            ["django", "orm"],
            "count() executes a single SELECT COUNT(*); the filter itself runs nothing until "
            "evaluated.",
        ),
        (
            MCQ,
            H,
            "Which setting must be a list of hostnames when DEBUG is False?",
            ["HOSTS", "SERVER_NAMES", "*ALLOWED_HOSTS", "TRUSTED_ORIGINS"],
            ["django", "deployment"],
        ),
        (
            MCQ,
            H,
            "In DRF, where should a counsellor's queryset be restricted to their own centre?",
            [
                "In the serializer's validate method",
                "*In the viewset's get_queryset",
                "In urls.py",
                "In the model's save",
            ],
            ["drf", "security"],
        ),
        (
            MCQ,
            H,
            "What does select_related do?",
            [
                "Caches the queryset",
                "*Follows foreign keys in the same query with a JOIN",
                "Runs one extra query per related object",
                "Filters related objects",
            ],
            ["django", "orm", "performance"],
        ),
        (TF, E, "Python uses indentation to define blocks.", True, ["python"]),
        (
            TF,
            M,
            "A Django template should hard-code URL paths rather than use the url tag.",
            False,
            ["django", "templates"],
        ),
        (
            TF,
            M,
            "A ModelSerializer validates incoming data as well as rendering outgoing data.",
            True,
            ["drf"],
        ),
        (
            TF,
            H,
            "Business rules that live only in a serializer are still applied by a management "
            "command that calls the model directly.",
            False,
            ["django", "architecture"],
        ),
        (SA, E, "Which keyword defines a function in Python?", ["def"], ["python"]),
        (
            SA,
            M,
            "Which manage.py command starts the development server?",
            ["runserver", "manage.py runserver", "python manage.py runserver"],
            ["django"],
        ),
        (
            SA,
            H,
            "Which WSGI server is commonly used to run Django behind nginx (name it)?",
            ["gunicorn"],
            ["deployment"],
        ),
        (
            LA,
            M,
            "Trace a request from the browser to a rendered Django template, naming each component "
            "it passes through.",
            None,
            ["django"],
        ),
        (
            LA,
            H,
            "Explain the N+1 query problem with an example and show how select_related and "
            "prefetch_related each solve it.",
            None,
            ["django", "orm", "performance"],
        ),
        (
            MULTI,
            M,
            "Which of these are built-in Python collection types?",
            ["*list", "*dict", "array", "*set"],
            ["python", "collections"],
        ),
        (
            MULTI,
            H,
            "Which of the following does manage.py check --deploy warn about?",
            [
                "*DEBUG = True",
                "*A missing SECURE_HSTS_SECONDS",
                "An unused app in INSTALLED_APPS",
                "*SESSION_COOKIE_SECURE not set",
            ],
            ["django", "deployment", "security"],
        ),
    ],
    "aws-solutions-architect": [
        (
            MCQ,
            E,
            "What is an availability zone?",
            ["A region", "*One or more data centres within a region", "An edge location", "A VPC"],
            ["aws", "fundamentals"],
        ),
        (
            MCQ,
            E,
            "Which service stores objects rather than blocks or files?",
            ["EBS", "EFS", "*S3", "FSx"],
            ["aws", "storage"],
        ),
        (
            MCQ,
            E,
            "Which service manages users, roles and permissions?",
            ["*IAM", "Cognito", "KMS", "Organizations"],
            ["aws", "iam"],
        ),
        (
            MCQ,
            E,
            "Which AWS region is in Mumbai?",
            ["ap-southeast-1", "*ap-south-1", "ap-east-1", "me-south-1"],
            ["aws", "fundamentals"],
        ),
        (
            MCQ,
            M,
            "What makes a subnet public?",
            [
                "It has a public name",
                "*Its route table sends 0.0.0.0/0 to an internet gateway",
                "It is in the default VPC",
                "Instances in it have security groups",
            ],
            ["aws", "vpc"],
        ),
        (
            MCQ,
            M,
            "Which is stateful?",
            ["Network ACL", "*Security group", "Route table", "Both"],
            ["aws", "vpc", "security"],
        ),
        (
            MCQ,
            M,
            "How should an EC2 instance get permission to read an S3 bucket?",
            [
                "Store access keys in a file on the instance",
                "*Attach an IAM role through an instance profile",
                "Make the bucket public",
                "Use the root account keys",
            ],
            ["aws", "iam"],
        ),
        (
            MCQ,
            M,
            "Which RDS feature gives automatic failover to a standby in another AZ?",
            ["Read replica", "*Multi-AZ", "Snapshot", "Aurora Serverless"],
            ["aws", "rds"],
        ),
        (
            MCQ,
            H,
            "An IAM policy allows s3:* and another attached policy denies s3:DeleteObject. What "
            "happens on a delete?",
            [
                "Allowed, the allow is more specific",
                "*Denied, an explicit deny always wins",
                "Depends on order",
                "Allowed for the root user only",
            ],
            ["aws", "iam"],
            "Evaluation: explicit deny, then allow, then implicit deny.",
        ),
        (
            MCQ,
            H,
            "A workload needs the lowest cost and tolerates interruption. Which pricing model "
            "fits?",
            ["On-Demand", "Reserved", "*Spot", "Dedicated Host"],
            ["aws", "ec2", "cost"],
        ),
        (
            MCQ,
            H,
            "Which service decouples two components with a queue?",
            ["SNS", "*SQS", "EventBridge", "Kinesis"],
            ["aws", "messaging"],
        ),
        (
            MCQ,
            H,
            "Which service gives a static anycast IP that routes TCP traffic to the nearest "
            "healthy region?",
            ["CloudFront", "Route 53", "*Global Accelerator", "Direct Connect"],
            ["aws", "networking"],
        ),
        (TF, E, "IAM is a global service, not a regional one.", True, ["aws", "iam"]),
        (
            TF,
            M,
            "A NAT gateway lets instances in a private subnet accept inbound connections from the "
            "internet.",
            False,
            ["aws", "vpc"],
        ),
        (
            TF,
            M,
            "Read replicas are for scaling reads, not for automatic failover.",
            True,
            ["aws", "rds"],
        ),
        (TF, H, "An S3 bucket name must be unique only within your account.", False, ["aws", "s3"]),
        (
            SA,
            E,
            "Which service is AWS's DNS service (name it)?",
            ["Route 53", "route53"],
            ["aws", "dns"],
        ),
        (
            SA,
            M,
            "Which AWS service runs code without provisioning servers (name it)?",
            ["Lambda", "AWS Lambda"],
            ["aws", "serverless"],
        ),
        (
            SA,
            H,
            "Which IAM API call lets a principal temporarily take on a role (give the action "
            "name)?",
            ["AssumeRole", "sts:AssumeRole"],
            ["aws", "iam"],
        ),
        (
            LA,
            M,
            "Design a VPC for a three-tier web application across two availability zones. Name the "
            "subnets, the gateways and what each route table contains.",
            None,
            ["aws", "vpc"],
        ),
        (
            LA,
            H,
            "A company wants the least operational overhead for a relational database with "
            "automatic failover and read scaling. Recommend a design and justify each choice "
            "against the alternatives.",
            None,
            ["aws", "rds", "architecture"],
        ),
        (
            MULTI,
            M,
            "Which of these are global services?",
            ["*IAM", "*CloudFront", "EC2", "*Route 53"],
            ["aws", "fundamentals"],
        ),
        (
            MULTI,
            H,
            "Which statements about S3 are true?",
            [
                "*Objects are stored across multiple AZs by default",
                "*Versioning can protect against accidental deletion",
                "S3 provides block storage for EC2",
                "*Lifecycle rules can move objects to Glacier",
            ],
            ["aws", "s3"],
        ),
    ],
    "mern-full-stack": [
        (
            MCQ,
            E,
            "Which of the four MERN letters is the database?",
            ["*M — MongoDB", "E — Express", "R — React", "N — Node"],
            ["mern"],
        ),
        (
            MCQ,
            E,
            "Which keyword declares a block-scoped constant in JavaScript?",
            ["var", "let", "*const", "static"],
            ["javascript"],
        ),
        (
            MCQ,
            E,
            "What does npm install express do?",
            [
                "Starts Express",
                "*Adds Express to the project's dependencies",
                "Creates an Express app",
                "Compiles Express",
            ],
            ["node", "npm"],
        ),
        (
            MCQ,
            E,
            "Which React hook stores state in a function component?",
            ["useEffect", "*useState", "useMemo", "useRef"],
            ["react", "hooks"],
        ),
        (
            MCQ,
            M,
            "Why can a single-threaded Node server handle many connections?",
            [
                "It uses many threads",
                "*It never blocks; I/O is asynchronous and callbacks run when ready",
                "It forks per request",
                "V8 is fast",
            ],
            ["node", "event-loop"],
        ),
        (
            MCQ,
            M,
            "What happens to an unhandled promise rejection in current Node versions?",
            ["It is logged and ignored", "*The process exits", "It is retried", "Nothing"],
            ["node", "async"],
        ),
        (
            MCQ,
            M,
            "In Mongoose, where are indexes declared?",
            ["In the controller", "*In the schema", "In package.json", "In the query"],
            ["mongodb", "mongoose"],
        ),
        (
            MCQ,
            M,
            "Which Express function signature identifies error-handling middleware?",
            ["(req, res)", "(req, res, next)", "*(err, req, res, next)", "(error)"],
            ["express"],
        ),
        (
            MCQ,
            H,
            "A useEffect that fetches data runs on every render. What is the most likely cause?",
            [
                "The API is slow",
                "*A missing or ever-changing dependency array",
                "React strict mode",
                "The component is not memoised",
            ],
            ["react", "hooks"],
            "Without a dependency array the effect runs after every render; an object literal in "
            "the array changes identity every render.",
        ),
        (
            MCQ,
            H,
            "When should a document be referenced rather than embedded in MongoDB?",
            [
                "Always",
                "*When it is large, unbounded or shared between parents",
                "When it is read with the parent",
                "Never",
            ],
            ["mongodb", "modelling"],
        ),
        (
            MCQ,
            H,
            "Promise.all([a(), b()]) compared with await a(); await b() when a and b are "
            "independent:",
            [
                "Is slower",
                "*Runs both concurrently and finishes in about the longer of the two",
                "Runs them in sequence",
                "Is identical",
            ],
            ["javascript", "async"],
        ),
        (
            MCQ,
            H,
            "Where should a JWT be verified in an Express API?",
            [
                "In the React app",
                "*In middleware before the protected route handlers",
                "In the database",
                "In package.json",
            ],
            ["express", "auth", "security"],
        ),
        (TF, E, "React re-renders a component when its state changes.", True, ["react"]),
        (TF, M, "A MongoDB document may be larger than 16 MB.", False, ["mongodb"]),
        (
            TF,
            M,
            "async/await pauses the whole Node thread until the awaited promise settles.",
            False,
            ["node", "async"],
        ),
        (
            TF,
            H,
            "Server data fetched from an API is best kept in React context rather than a query "
            "cache.",
            False,
            ["react", "state"],
        ),
        (SA, E, "Which command initialises a new package.json (two words)?", ["npm init"], ["npm"]),
        (
            SA,
            M,
            "Which MongoDB feature processes documents through a sequence of stages such as $match "
            "and $group?",
            ["aggregation pipeline", "aggregation", "the aggregation pipeline"],
            ["mongodb"],
        ),
        (
            SA,
            H,
            "Which React hook returns a memoised callback so a child does not re-render "
            "needlessly?",
            ["useCallback"],
            ["react", "hooks", "performance"],
        ),
        (
            LA,
            M,
            "Explain the Node event loop and why CPU-heavy work is the one thing it handles badly.",
            None,
            ["node", "event-loop"],
        ),
        (
            LA,
            H,
            "Design the data model for a training centre's batches, students and attendance in "
            "MongoDB. State what you embed, what you reference, and why.",
            None,
            ["mongodb", "modelling"],
        ),
        (
            MULTI,
            M,
            "Which of these are valid HTTP methods used in a REST API?",
            ["*GET", "*POST", "FETCH", "*DELETE"],
            ["http", "rest"],
        ),
        (
            MULTI,
            H,
            "Which statements about React state are true?",
            [
                "*State should live at the lowest component that needs it",
                "*Two siblings share state through their parent",
                "Every piece of state belongs in a global store",
                "*Server data belongs in a query cache",
            ],
            ["react", "state"],
        ),
    ],
}

#: The shared bank (``course=None``): general computing and study skills that
#: any exam may draw from alongside its course's own questions.
SHARED_QUESTIONS: list[Item] = [
    (MCQ, E, "How many bits are in a byte?", ["4", "*8", "16", "32"], ["fundamentals"]),
    (
        MCQ,
        E,
        "Which of these is a version control system?",
        ["*Git", "Jira", "Docker", "nginx"],
        ["fundamentals", "git"],
    ),
    (
        MCQ,
        M,
        "What does HTTP status 404 mean?",
        ["Server error", "Unauthorised", "*Not found", "Redirect"],
        ["http", "fundamentals"],
    ),
    (
        MCQ,
        M,
        "Which port does HTTPS use by default?",
        ["80", "*443", "8080", "22"],
        ["networking", "fundamentals"],
    ),
    (
        MCQ,
        H,
        "What is the decimal value of the binary number 10110?",
        ["20", "*22", "24", "26"],
        ["fundamentals", "binary"],
    ),
    (
        TF,
        E,
        "SSH encrypts the traffic between client and server.",
        True,
        ["security", "fundamentals"],
    ),
    (
        TF,
        M,
        "A strong password is one that is reused across services so it is not forgotten.",
        False,
        ["security"],
    ),
    (
        SA,
        E,
        "What does the acronym API stand for?",
        ["application programming interface"],
        ["fundamentals"],
    ),
    (SA, M, "Which command shows the commit history in Git (two words)?", ["git log"], ["git"]),
    (
        LA,
        M,
        "Describe how you would approach a problem you have never seen before during an exam, in "
        "four steps.",
        None,
        ["study-skills"],
    ),
]

#: Written for RHEL 7, retired when the syllabus moved to RHEL 9. Kept in the
#: bank, inactive, so the question list shows a retired row and the exam
#: drawer proves it skips one.
RETIRED_QUESTION: tuple[str, Item] = (
    "rhcsa",
    (
        MCQ,
        E,
        "Which command shows network interface addresses on RHEL 7?",
        ["*ifconfig", "ip addr", "netstat -i", "nmcli"],
        ["networking", "rhel7"],
        "Retired: ifconfig is not installed by default on RHEL 8 and later; the answer is now ip "
        "addr.",
    ),
)


__all__ = [
    "CATEGORIES",
    "COURSES",
    "DOCS_HOST",
    "POLICY_COURSE",
    "POLICY_RULES",
    "QUESTIONS",
    "RETIRED_QUESTION",
    "SHARED_QUESTIONS",
    "SITP_PREFIX",
    "CourseSpec",
    "LessonSpec",
    "ModuleSpec",
    "Track",
    "sitp_lessons",
    "track_for",
]
