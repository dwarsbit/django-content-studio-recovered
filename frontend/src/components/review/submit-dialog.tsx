import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

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
import { useHttp } from "@/hooks/use-http";
import type { ReviewDetails } from "@/types";

const ANYONE = "anyone";

/**
 * Submit for review (again): who reviews it, anyone who can publish or
 * one of them, and a note for the reviewer.
 */
export function SubmitDialog({
  open,
  onOpenChange,
  ...props
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  name: string;
  // The object's API path.
  resourcePath: string;
  again: boolean;
  live: boolean;
  isPending: boolean;
  onSubmit(reviewer: string | null, note: string): Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {/* Mounted per opening, so it starts empty. */}
        {open && <SubmitForm {...props} onCancel={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function SubmitForm({
  name,
  resourcePath,
  again,
  live,
  isPending,
  onCancel,
  onSubmit,
}: {
  name: string;
  resourcePath: string;
  again: boolean;
  live: boolean;
  isPending: boolean;
  onCancel(): void;
  onSubmit(reviewer: string | null, note: string): Promise<void>;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [reviewer, setReviewer] = useState(ANYONE);
  const [note, setNote] = useState("");
  const { data } = useQuery({
    queryKey: ["review", resourcePath, "reviewers"],
    async queryFn() {
      const { data } = await http.get<ReviewDetails>(`${resourcePath}/review`, {
        params: { include: "reviewers" },
      });
      return data;
    },
  });
  const reviewers = data?.reviewers ?? [];
  const picked = reviewers.find((person) => String(person.id) === reviewer);

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {t(again ? "review.submit_again" : "review.submit")}
        </DialogTitle>
        <DialogDescription>
          {t(
            live
              ? "review.submit_dialog.description_live"
              : "review.submit_dialog.description",
            { name },
          )}
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="review-reviewer">
            {t("review.submit_dialog.reviewer")}
          </Label>
          <Select value={reviewer} onValueChange={setReviewer}>
            <SelectTrigger
              id="review-reviewer"
              className="w-full"
              data-testid="review-reviewer"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANYONE}>{t("review.anyone")}</SelectItem>
              {reviewers.map((person) => (
                <SelectItem key={person.id} value={String(person.id)}>
                  <UserAvatar
                    name={person.name}
                    initials={person.initials}
                    src={person.avatar}
                    className="size-5"
                  />
                  {person.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            {picked
              ? t("review.submit_dialog.reviewer_hint", { name: picked.name })
              : t("review.submit_dialog.anyone_hint")}
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="review-note">{t("review.submit_dialog.note")}</Label>
          <Textarea
            id="review-note"
            value={note}
            maxLength={10000}
            rows={3}
            placeholder={t("review.submit_dialog.note_placeholder")}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          isLoading={isPending}
          data-testid="review-submit"
          onClick={() => onSubmit(picked ? String(picked.id) : null, note)}
        >
          {t(again ? "review.submit_again" : "review.submit")}
        </Button>
      </DialogFooter>
    </>
  );
}
