import * as R from "ramda";

import { usePublishing } from "@/components/publishing/publishing";
import { PublishingCard } from "@/components/publishing/publishing-card";
import {
  MockCommentsCard,
  MockPublishingCard,
  useReviewScene,
} from "@/components/review/review-mock";
import { cn } from "@/lib/utils";
import type { Model } from "@/types";

import { Conditional } from "./conditional";
import { fieldNames } from "./conditional-fields";
import { EditPlacementContext } from "./edit-placement";
import { FormSet, HIDE_EMPTY_FORM_SET } from "./form-set";

export function Aside({
  model,
  hiddenFields,
}: {
  model: Model;
  hiddenFields: string[];
}) {
  const {
    admin: {
      edit: { sidebar },
    },
  } = model;
  // Studios with publishing open the sidebar with the Publishing card.
  const publishing = usePublishing();
  // MOCK: the review workflow screens.
  const scene = useReviewScene();
  const hasSidebar = (!R.isEmpty(sidebar) && !R.isNil(sidebar)) || !!publishing;

  return (
    hasSidebar && (
      <EditPlacementContext.Provider value="sidebar">
        <aside className="space-y-4">
          {scene ? <MockPublishingCard scene={scene} /> : <PublishingCard />}
          {scene === "comments" && <MockCommentsCard />}
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
