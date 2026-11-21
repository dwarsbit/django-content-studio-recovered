import * as R from "ramda";

import { CommentsCard } from "@/components/comments/comments-card";
import { usePublishing } from "@/components/publishing/publishing";
import { PublishingCard } from "@/components/publishing/publishing-card";
import { cn } from "@/lib/utils";
import type { Id, Model } from "@/types";

import { Conditional } from "./conditional";
import { fieldNames } from "./conditional-fields";
import { EditPlacementContext } from "./edit-placement";
import { FormSet, HIDE_EMPTY_FORM_SET } from "./form-set";

export function Aside({
  model,
  hiddenFields,
  commentsOn,
}: {
  model: Model;
  hiddenFields: string[];
  // The saved object the Comments card is for: not on new objects,
  // inline rows or dialogs.
  commentsOn?: Id | null;
}) {
  const {
    admin: {
      edit: { sidebar },
    },
  } = model;
  // Studios with publishing open the sidebar with the Publishing card.
  const publishing = usePublishing();
  const comments = !!model.admin.comments && !R.isNil(commentsOn);
  const hasSidebar =
    (!R.isEmpty(sidebar) && !R.isNil(sidebar)) || !!publishing || comments;

  return (
    hasSidebar && (
      <EditPlacementContext.Provider value="sidebar">
        <aside className="space-y-4">
          <PublishingCard />
          {comments && <CommentsCard model={model} id={commentsOn!} />}
          {(sidebar ?? []).map((formSet, idx) => (
            <Conditional
              key={idx}
              when={formSet.when}
              fields={fieldNames(formSet.fields)}
            >
              <section
                className={cn(
                  "rounded-lg border bg-card shadow-xs w-full",
                  HIDE_EMPTY_FORM_SET,
                )}
              >
                <FormSet
                  model={model}
                  formSet={formSet}
                  hiddenFields={hiddenFields}
                />
              </section>
            </Conditional>
          ))}
        </aside>
      </EditPlacementContext.Provider>
    )
  );
}
