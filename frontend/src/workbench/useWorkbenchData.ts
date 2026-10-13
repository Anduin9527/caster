import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ServerCharacter } from "../library";
import type { PromptSettings } from "../production";
import { workbenchKeys, workbenchQueries } from "./queries";

export function useWorkbenchData(characterId: string) {
  const client = useQueryClient();
  const charactersQuery = useQuery(workbenchQueries.characters());
  const snapshotQuery = useQuery(workbenchQueries.snapshot(characterId));
  const capabilitiesQuery = useQuery(workbenchQueries.capabilities());
  const presetsQuery = useQuery(workbenchQueries.presets());
  const settingsQuery = useQuery(workbenchQueries.promptSettings());
  const snapshot = snapshotQuery.data ?? null;
  const characters = useMemo(
    () =>
      (charactersQuery.data ?? []).map(
        (character) =>
          snapshot?.characters.find((row) => row.id === character.id) ??
          character,
      ),
    [charactersQuery.data, snapshot],
  );
  const presets = useMemo(
    () =>
      (presetsQuery.data ?? []).filter(
        (preset) => preset.format === "pose_studio_3d",
      ),
    [presetsQuery.data],
  );
  const error =
    charactersQuery.error ?? capabilitiesQuery.error ?? snapshotQuery.error;

  return {
    characters,
    charactersLoaded: charactersQuery.isSuccess,
    snapshot,
    connected:
      capabilitiesQuery.isSuccess &&
      Boolean(
        capabilitiesQuery.data.selection && capabilitiesQuery.data.batches,
      ) &&
      (!characterId || snapshotQuery.isSuccess),
    online:
      capabilitiesQuery.isSuccess && capabilitiesQuery.data.generation_online,
    error: error?.message ?? "",
    presets,
    presetError: presetsQuery.isError
      ? "姿态库连接失败，正在重新连接。"
      : presetsQuery.isSuccess && !presets.length
        ? "姿态库暂不可用，请稍后重试。"
        : "",
    promptSettings: settingsQuery.data ?? null,
    promptSettingsError: settingsQuery.error?.message ?? "",
    refresh: () => client.invalidateQueries({ queryKey: workbenchKeys.all }),
    setCharacters: (
      update:
        ServerCharacter[] | ((rows: ServerCharacter[]) => ServerCharacter[]),
    ) =>
      client.setQueryData<ServerCharacter[]>(
        workbenchKeys.characters,
        (rows = []) => (typeof update === "function" ? update(rows) : update),
      ),
    setPromptSettings: (settings: PromptSettings) =>
      client.setQueryData(workbenchKeys.promptSettings, settings),
  };
}
