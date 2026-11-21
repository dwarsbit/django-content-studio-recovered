/**
 * MOCK, not for merge: the review workflow's screens with made-up
 * data, for the mockup screenshots. `?review=<scene>` on an edit page,
 * the article list (`list`) or the dashboard (`dash`) turns it on;
 * `&dialog=submit|review` opens a dialog.
 */
import dayjs from "dayjs";
import { type ReactNode, useState } from "react";
import {
  PiArrowSquareOutBold,
  PiArrowUUpLeftBold,
  PiArrowsLeftRightBold,
  PiAtBold,
  PiCalendarBlankBold,
  PiChatCircleTextBold,
  PiCheckBold,
  PiInfoBold,
  PiPaperPlaneRightBold,
  PiPaperPlaneTiltBold,
  PiSealCheckBold,
} from "react-icons/pi";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { UserAvatar } from "@/components/ui/user-avatar";
import { cn } from "@/lib/utils";
import { diffWords } from "@/lib/word-diff";

export type Scene =
  | "pending"
  | "submit"
  | "submitted"
  | "reviewer"
  | "changes"
  | "comments"
  | "list"
  | "dash";

const SCENES: Scene[] = [
  "pending",
  "submit",
  "submitted",
  "reviewer",
  "changes",
  "comments",
  "list",
  "dash",
];

function param(name: string) {
  return typeof window === "undefined"
    ? null
    : new URLSearchParams(window.location.search).get(name);
}

export function useReviewScene(): Scene | null {
  const value = param("review") as Scene | null;
  return value && SCENES.includes(value) ? value : null;
}

const ago = (minutes: number) => dayjs().subtract(minutes, "minute").fromNow();

const PEOPLE = {
  sam: "Sam Okafor",
  priya: "Priya Raman",
  maya: "Maya Lindqvist",
  jonas: "Jonas Weber",
};

/* ------------------------------------------------------------------ */
/* Badges and the header                                               */
/* ------------------------------------------------------------------ */

export function ReviewBadge({
  kind,
  className,
}: {
  kind: "in_review" | "changes_requested" | "unpublished";
  className?: string;
}) {
  const label = {
    in_review: "In review",
    changes_requested: "Changes requested",
    unpublished: "Unpublished changes",
  }[kind];
  const tone = {
    in_review: "purple",
    changes_requested: "red",
    unpublished: "yellow",
  }[kind] as "purple" | "red" | "yellow";

  return (
    <Badge tone={tone} className={className}>
      {label}
    </Badge>
  );
}

function StateBadge({ state }: { state: "draft" | "published" }) {
  return (
    <Badge tone={state === "draft" ? "gray" : "green"}>
      {state === "draft" ? "Draft" : "Published"}
    </Badge>
  );
}

function Dot({ className }: { className: string }) {
  return (
    <span className="h-5 flex items-center shrink-0">
      <span className={cn("size-1.5 rounded-full", className)} />
    </span>
  );
}

/** Next to the title: the state badge and the review status. */
export function MockHeaderMeta({
  scene,
  status,
}: {
  scene: Scene;
  // The real "Last edited" status.
  status: ReactNode;
}) {
  const line =
    "flex items-center gap-x-1.5 h-5 overflow-hidden shrink-[9999] text-muted-foreground text-sm whitespace-nowrap ml-1";

  switch (scene) {
    case "pending":
      return (
        <>
          <StateBadge state="published" />
          <div className={line}>
            <Dot className="bg-warning" />
            <span>Unpublished changes</span>
          </div>
        </>
      );
    case "reviewer":
      return (
        <>
          <StateBadge state="published" />
          <div className={line}>
            <Dot className="bg-violet-500" />
            <span>Changes in review</span>
          </div>
        </>
      );
    case "submitted":
      return (
        <>
          <ReviewBadge kind="in_review" />
          {status}
        </>
      );
    case "changes":
    case "comments":
      return (
        <>
          <ReviewBadge kind="changes_requested" />
          {status}
        </>
      );
    default:
      return (
        <>
          <StateBadge state="draft" />
          {status}
        </>
      );
  }
}

/** Whether Save steps back (outline) for a primary review button. */
export function hasPrimary(scene: Scene) {
  return scene !== "submitted";
}

/** The header's primary button, next to Save, and its dialog. */
export function MockPrimaryButton({ scene }: { scene: Scene }) {
  const initial = param("dialog");
  const [submitOpen, setSubmitOpen] = useState(initial === "submit");
  const [reviewOpen, setReviewOpen] = useState(initial === "review");

  let button: ReactNode = null;

  if (scene === "pending") {
    button = (
      <Button>
        <PiPaperPlaneTiltBold />
        Publish changes
      </Button>
    );
  } else if (scene === "submit") {
    button = (
      <Button onClick={() => setSubmitOpen(true)}>
        <PiPaperPlaneRightBold />
        Submit for review
      </Button>
    );
  } else if (scene === "changes" || scene === "comments") {
    button = (
      <Button onClick={() => setSubmitOpen(true)}>
        <PiPaperPlaneRightBold />
        Submit again
      </Button>
    );
  } else if (scene === "reviewer") {
    button = (
      <Button onClick={() => setReviewOpen(true)}>
        <PiSealCheckBold />
        Review
      </Button>
    );
  }

  return (
    <>
      {button}
      <SubmitDialog open={submitOpen} onOpenChange={setSubmitOpen} />
      <ReviewDialog open={reviewOpen} onOpenChange={setReviewOpen} />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* The Publishing card                                                 */
/* ------------------------------------------------------------------ */

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 min-h-8">
      <span className="text-sm text-muted-foreground shrink-0">{label}</span>
      <div className="flex items-center gap-1.5 text-sm font-medium min-w-0">
        {children}
      </div>
    </div>
  );
}

function Person({ name, suffix }: { name: string; suffix?: string }) {
  return (
    <span className="flex items-center gap-1.5 min-w-0">
      <UserAvatar name={name} className="size-5" />
      <span className="truncate">{name}</span>
      {suffix && (
        <span className="text-muted-foreground font-normal shrink-0">
          {suffix}
        </span>
      )}
    </span>
  );
}

function Note({
  name,
  when,
  action,
  children,
}: {
  name: string;
  when: string;
  action?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md bg-muted/60 px-3 py-2.5 text-sm space-y-1">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <UserAvatar name={name} className="size-4" />
        <span className="font-medium text-foreground">{name}</span>
        {action && <span>{action}</span>}
        <span>·</span>
        <span>{when}</span>
      </div>
      <p className="leading-relaxed">{children}</p>
    </div>
  );
}

function Card({ badge, children }: { badge: ReactNode; children: ReactNode }) {
  return (
    <section
      className="rounded-lg border bg-card shadow-xs w-full"
      data-testid="publishing-card"
    >
      <div className="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h4 className="font-semibold">Publishing</h4>
        {badge}
      </div>
      <div className="p-5 pt-3 space-y-1">{children}</div>
    </section>
  );
}

const LIVE_SINCE = "Thu 19 Nov, 09:11";
const SUBMIT_NOTE =
  "Ready for a look. I wasn't sure about the headline, happy to change it.";
const CHANGES_NOTE =
  "Lovely piece. Two things before it goes out: the headline promises a guide, so add when to go and where to stand, and the aurora forecast link returns a 404.";
const REVIEW_NOTE =
  "Tightened the intro and fixed the train times for the winter timetable.";

function ReviewSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="pt-3 mt-2 border-t space-y-2">
      <div className="text-sm font-semibold pt-1">{title}</div>
      {children}
    </div>
  );
}

export function MockPublishingCard({ scene }: { scene: Scene }) {
  if (scene === "pending") {
    return (
      <Card badge={<StateBadge state="published" />}>
        <Row label="Published">{LIVE_SINCE}</Row>
        <Row label="Unpublish on">
          <span className="text-muted-foreground font-normal">Never</span>
        </Row>
        <ReviewSection title="Unpublished changes">
          <div className="text-sm">
            <span className="font-medium">Title, Intro and Body</span>
            <span className="text-muted-foreground">
              {" "}
              · saved by {PEOPLE.maya} {ago(12)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground flex gap-1.5">
            <PiInfoBold className="shrink-0 mt-0.5" />
            Readers see the published version until the changes are published.
          </p>
          <div className="flex gap-2 pt-1">
            <Button variant="outline" size="sm" className="flex-1">
              <PiArrowsLeftRightBold />
              Compare
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex-1 text-destructive"
            >
              Discard
            </Button>
          </div>
        </ReviewSection>
      </Card>
    );
  }

  if (scene === "submit") {
    return (
      <Card badge={<StateBadge state="draft" />}>
        <Row label="Publish on">
          <span className="text-muted-foreground font-normal">
            After review
          </span>
        </Row>
        <Row label="Unpublish on">
          <span className="text-muted-foreground font-normal">Never</span>
        </Row>
        <p className="text-xs text-muted-foreground flex gap-1.5 pt-2">
          <PiInfoBold className="shrink-0 mt-0.5" />
          Submit it for review: someone who can publish approves it and
          publishes it.
        </p>
      </Card>
    );
  }

  if (scene === "submitted") {
    return (
      <Card badge={<ReviewBadge kind="in_review" />}>
        <Row label="Publish on">
          <span className="text-muted-foreground font-normal">
            After review
          </span>
        </Row>
        <ReviewSection title="Review">
          <Row label="Submitted">
            <Person name="You" suffix={ago(2)} />
          </Row>
          <Row label="Reviewer">
            <Person name={PEOPLE.priya} />
          </Row>
          <Note name="You" when={ago(2)}>
            {SUBMIT_NOTE}
          </Note>
          <div className="pt-2">
            <Button variant="outline" size="sm" className="w-full">
              Withdraw from review
            </Button>
          </div>
        </ReviewSection>
      </Card>
    );
  }

  if (scene === "reviewer") {
    return (
      <Card badge={<StateBadge state="published" />}>
        <Row label="Published">{LIVE_SINCE}</Row>
        <Row label="Unpublish on">
          <span className="text-muted-foreground font-normal">Never</span>
        </Row>
        <ReviewSection title="Changes in review">
          <Row label="Submitted">
            <Person name={PEOPLE.maya} />
          </Row>
          <Row label="Reviewer">
            <span className="font-normal text-muted-foreground">
              Anyone who can publish
            </span>
          </Row>
          <Note name={PEOPLE.maya} when={ago(25)}>
            {REVIEW_NOTE}
          </Note>
          <div className="flex gap-2 pt-2">
            <Button variant="outline" size="sm" className="flex-1">
              Request changes
            </Button>
            <Button variant="outline" size="sm" className="flex-1">
              <PiCheckBold />
              Approve…
            </Button>
          </div>
        </ReviewSection>
      </Card>
    );
  }

  // changes, comments
  return (
    <Card badge={<ReviewBadge kind="changes_requested" />}>
      <Row label="Publish on">
        <span className="text-muted-foreground font-normal">After review</span>
      </Row>
      <ReviewSection title="Changes requested">
        <Row label="By">
          <Person name={PEOPLE.priya} suffix={ago(5)} />
        </Row>
        {scene === "comments" ? (
          <p className="text-xs text-muted-foreground flex gap-1.5">
            <PiChatCircleTextBold className="shrink-0 mt-0.5" />
            Priya's note is in the comments below.
          </p>
        ) : (
          <Note name={PEOPLE.priya} when={ago(5)}>
            {CHANGES_NOTE}
          </Note>
        )}
        <p className="text-xs text-muted-foreground pt-1">
          Submitted by you {ago(70)}. Submit again when it's ready.
        </p>
      </ReviewSection>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Comments (a feature of its own; review posts its notes here)        */
/* ------------------------------------------------------------------ */

function Comment({
  name,
  when,
  tag,
  children,
}: {
  name: string;
  when: string;
  tag?: ReactNode;
  children: ReactNode;
}) {
  return (
    <li className="flex gap-2.5 py-3">
      <UserAvatar name={name} className="size-7 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-1.5 text-sm flex-wrap">
          <span className="font-medium">{name}</span>
          <span className="text-xs text-muted-foreground">{when}</span>
        </div>
        {tag}
        <p className="text-sm leading-relaxed">{children}</p>
      </div>
    </li>
  );
}

function ActionTag({
  kind,
  children,
}: {
  kind: "in_review" | "changes_requested";
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1 text-xs font-medium",
        kind === "in_review"
          ? "text-violet-700 dark:text-violet-300"
          : "text-red-700 dark:text-red-300",
      )}
    >
      {kind === "in_review" ? (
        <PiPaperPlaneRightBold />
      ) : (
        <PiArrowUUpLeftBold />
      )}
      {children}
    </div>
  );
}

export function MockCommentsCard() {
  return (
    <section className="rounded-lg border bg-card shadow-xs w-full">
      <div className="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h4 className="font-semibold flex items-center gap-2">
          Comments
          <span className="rounded-full bg-muted text-muted-foreground px-1.5 text-[11px] font-semibold leading-[18px] tabular-nums">
            3
          </span>
        </h4>
        <Button variant="ghost" size="xs" className="text-muted-foreground">
          1 resolved
        </Button>
      </div>
      <ul className="px-5 divide-y">
        <Comment
          name={PEOPLE.sam}
          when={ago(70)}
          tag={<ActionTag kind="in_review">Submitted for review</ActionTag>}
        >
          {SUBMIT_NOTE}
        </Comment>
        <Comment
          name={PEOPLE.priya}
          when={ago(5)}
          tag={
            <ActionTag kind="changes_requested">Requested changes</ActionTag>
          }
        >
          {CHANGES_NOTE}
        </Comment>
        <Comment name={PEOPLE.jonas} when={ago(2)}>
          <span className="text-violet-700 dark:text-violet-300 font-medium">
            @Sam
          </span>{" "}
          the forecast page moved to /aurora/forecast. Happy to fix the link if
          you want.
        </Comment>
      </ul>
      <div className="px-5 pb-5 pt-1 space-y-2">
        <Textarea
          rows={2}
          placeholder="Write a comment. Use @ to mention someone."
          className="resize-none text-sm"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <PiAtBold />
            Only people with access to this article see comments.
          </span>
          <Button size="sm" variant="outline">
            Comment
          </Button>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Dialogs                                                             */
/* ------------------------------------------------------------------ */

function SubmitDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Submit for review</DialogTitle>
          <DialogDescription>
            Someone who can publish reviews it, then publishes or schedules it.
            You can keep editing while it's in review.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Reviewer</Label>
            <Select defaultValue="priya">
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="anyone">
                  Anyone who can publish (3)
                </SelectItem>
                <SelectItem value="priya">{PEOPLE.priya}</SelectItem>
                <SelectItem value="alex">Alex Morgan</SelectItem>
                <SelectItem value="jonas">{PEOPLE.jonas}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Only Priya is notified. Anyone who can publish can still review
              it.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Note for the reviewer</Label>
            <Textarea rows={3} defaultValue={SUBMIT_NOTE} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline">Cancel</Button>
          <Button>
            <PiPaperPlaneRightBold />
            Submit for review
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const CHANGES: { label: string; before: string; after: string }[] = [
  {
    label: "Title",
    before: "Why the best trips start with a slow train",
    after: "Why the best journeys start with a slow train",
  },
  {
    label: "Intro",
    before:
      "Fast trains get you there. Slow trains give you the country in between, and a seat by the window to watch it pass.",
    after:
      "Fast trains get you there. Slow trains give you the country in between: the villages, the rivers, and a seat by the window to watch it all pass.",
  },
  {
    label: "Body",
    before:
      "The morning service leaves at 07:12 and reaches the coast just after eleven. Bring a book, but you will not read it.",
    after:
      "From December the morning service leaves at 07:40 and reaches the coast just before noon. Bring a book, but you will not read it.",
  },
];

function Diff({ before, after }: { before: string; after: string }) {
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm leading-relaxed">
      {diffWords(before, after).map((part, index) =>
        part.type === "same" ? (
          <span key={index}>{part.text}</span>
        ) : part.type === "removed" ? (
          <del
            key={index}
            className="bg-red-500/15 text-red-700 dark:text-red-300 rounded-sm px-0.5"
          >
            {part.text}
          </del>
        ) : (
          <ins
            key={index}
            className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 no-underline rounded-sm px-0.5"
          >
            {part.text}
          </ins>
        ),
      )}
    </div>
  );
}

function ReviewDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Review changes</DialogTitle>
          <DialogDescription>
            Why the best trips start with a slow train · submitted by{" "}
            {PEOPLE.maya} {ago(25)}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 max-h-[60vh] overflow-y-auto -mx-1 px-1">
          <Note name={PEOPLE.maya} when={ago(25)}>
            {REVIEW_NOTE}
          </Note>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">
                3 fields changed against the published version
              </div>
              <Button
                variant="ghost"
                size="xs"
                className="text-muted-foreground"
              >
                Preview
                <PiArrowSquareOutBold />
              </Button>
            </div>
            {CHANGES.map((change) => (
              <div key={change.label} className="space-y-1.5">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {change.label}
                </div>
                <Diff before={change.before} after={change.after} />
              </div>
            ))}
          </div>
          <div className="space-y-2">
            <Label>Note</Label>
            <Textarea
              rows={2}
              placeholder="Required when you request changes."
            />
          </div>
        </div>
        <DialogFooter className="sm:justify-between">
          <Button variant="outline" className="text-destructive">
            Request changes
          </Button>
          <div className="flex gap-2">
            <Button variant="outline">
              <PiCalendarBlankBold />
              Approve and schedule…
            </Button>
            <Button>
              <PiCheckBold />
              Approve and publish
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* The list's Status column and the dashboard                          */
/* ------------------------------------------------------------------ */

const LIST_STATES: Record<
  string,
  "in_review" | "changes_requested" | "unpublished"
> = {
  "22": "in_review",
  "21": "in_review",
  "19": "unpublished",
  "17": "changes_requested",
};

/** The second badge a row gets in the list mock. */
export function listReviewState(id?: string) {
  return useReviewSceneStatic() === "list" && id ? LIST_STATES[id] : undefined;
}

function useReviewSceneStatic() {
  return param("review");
}

const QUEUE = [
  {
    title: "Why the best trips start with a slow train",
    by: PEOPLE.maya,
    minutes: 25,
    kind: "Changes",
    to: "/content/demo_blog.article/21",
  },
  {
    title: "Field notes: first snow on the pass",
    by: PEOPLE.sam,
    minutes: 50,
    kind: "Changes",
    to: "/content/demo_blog.article/22",
  },
  {
    title: "A weekend guide to the northern lights",
    by: PEOPLE.sam,
    minutes: 70,
    kind: "New",
    to: "/content/demo_blog.article/1",
  },
];

export function ReviewQueueWidget() {
  return (
    <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold truncate flex items-center gap-2">
            Waiting for your review
            <span className="rounded-full bg-primary text-primary-foreground px-1.5 text-[11px] font-semibold leading-[18px] tabular-nums">
              3
            </span>
          </h2>
          <div className="text-xs text-muted-foreground truncate">
            Submitted for review, oldest first
          </div>
        </div>
      </div>
      <ul className="border-t p-1.5">
        {[...QUEUE].reverse().map((item) => (
          <li key={item.title}>
            <div className="flex items-center gap-3 rounded-md px-2.5 py-2 hover:bg-accent">
              <UserAvatar name={item.by} className="size-8 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{item.title}</div>
                <div className="text-xs text-muted-foreground truncate">
                  {item.by} · {ago(item.minutes)}
                </div>
              </div>
              <Badge tone={item.kind === "New" ? "blue" : "purple"}>
                {item.kind === "New" ? "New article" : "Changes"}
              </Badge>
              <Button variant="outline" size="xs">
                Review
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
