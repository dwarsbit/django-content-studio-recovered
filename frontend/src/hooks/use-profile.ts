import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuth } from "@/auth";
import {
  type AnalyticsRange,
  type Interval,
  type MetricData,
  rangeParams,
  type TimeseriesPoint,
} from "@/components/analytics/data";
import type { SaveMode } from "@/components/content-editor/save-button";
import { useHttp } from "@/hooks/use-http";
import type { ProfileTwoFactor } from "@/pages/(studio)/profile/_components/two-factor-card";
import type { FormField } from "@/types";

export interface ProfileUser {
  id: string | number;
  username: string;
  name: string;
  email: string;
  initials: string;
  avatar: string | null;
  is_superuser: boolean;
  groups: string[];
  date_joined: string | null;
  last_login: string | null;
}

export interface Profile {
  user: ProfileUser;
  // The site's profile fields, as edit page fields.
  fields: FormField[];
  values: Record<string, unknown>;
  // Whether the user can change their password here.
  password: boolean;
  // Two-factor login, when the two-factor app is installed.
  two_factor?: ProfileTwoFactor | null;
  // The editor's preferences, when the preferences app is installed.
  preferences?: ProfilePreferences | null;
}

// The editor's own settings for the admin.
export interface ProfilePreferences {
  // What the edit page's Save button does.
  save_action: SaveMode;
}

export type ProfileMetric = "total" | "created" | "updated" | "deleted";

export interface ProfileActivity {
  range: { start: string; end: string; interval: Interval };
  metrics: (MetricData & { key: ProfileMetric })[];
  series: Record<ProfileMetric, TimeseriesPoint[]>;
  models: { key: string; label: string; value: number }[];
}

export interface RecentItem {
  model: string;
  model_label: string;
  id: string;
  title: string;
  action: "created" | "updated" | "deleted";
  timestamp: string;
  thumbnail: string | null;
  // Whether the object has an edit page to link to.
  link: boolean;
}

const PROFILE_KEY = ["profile"];

export function useProfile({ enabled = true }: { enabled?: boolean } = {}) {
  const http = useHttp();

  return useQuery({
    enabled,
    retry: false,
    queryKey: PROFILE_KEY,
    async queryFn() {
      const { data } = await http.get<Profile>("/profile");

      return data;
    },
  });
}

export function useProfileActivity(range: AnalyticsRange) {
  const http = useHttp();
  const params = rangeParams(range);

  return useQuery({
    retry: false,
    queryKey: [...PROFILE_KEY, "activity", params],
    placeholderData: keepPreviousData,
    async queryFn() {
      const { data } = await http.get<ProfileActivity>("/profile/activity", {
        params,
      });

      return data;
    },
  });
}

export function useRecentContent(limit = 10) {
  const http = useHttp();

  return useQuery({
    retry: false,
    queryKey: [...PROFILE_KEY, "recent", limit],
    async queryFn() {
      const { data } = await http.get<{ items: RecentItem[] }>(
        "/profile/recent",
        { params: { limit } },
      );

      return data.items;
    },
  });
}

/** Saves the profile fields; the user menu shows the new name. */
export function useUpdateProfile() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn(values: Record<string, unknown>) {
      const { data } = await http.patch<Profile>("/profile", values);

      return data;
    },
    async onSuccess(data) {
      queryClient.setQueryData(PROFILE_KEY, data);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

/** Saves preferences; the edit pages follow them at once. */
export function useUpdatePreferences() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn(values: Partial<ProfilePreferences>) {
      const { data } = await http.post<ProfilePreferences>(
        "/profile/preferences",
        values,
      );

      return data;
    },
    onSuccess(preferences) {
      queryClient.setQueryData<Profile>(PROFILE_KEY, (profile) =>
        profile ? { ...profile, preferences } : profile,
      );
    },
  });
}

/**
 * The preferences of the signed-in user: the defaults until loaded, and
 * without the preferences app.
 */
export function usePreferences({
  enabled = true,
}: { enabled?: boolean } = {}): ProfilePreferences {
  const { data } = useProfile({ enabled });

  return { save_action: data?.preferences?.save_action ?? "save" };
}

/**
 * Changes the password. Every token from before is void after it, so
 * the session continues with the access token the response carries.
 */
export function useChangePassword() {
  const http = useHttp();
  const { setToken } = useAuth();

  return useMutation({
    async mutationFn(values: {
      current_password: string;
      new_password: string;
    }) {
      const { data } = await http.post<{ access: string }>(
        "/profile/password",
        values,
      );

      return data;
    },
    onSuccess(data) {
      setToken(data.access);
    },
  });
}
