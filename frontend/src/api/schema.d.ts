export interface paths {
    "/api/v1/agent/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_api_v1_agent_conversations_get"];
        put?: never;
        /** Create Conversation */
        post: operations["create_conversation_api_v1_agent_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Conversation */
        get: operations["read_conversation_api_v1_agent_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/conversations/{conversation_id}/character": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Rebind Character */
        put: operations["rebind_character_api_v1_agent_conversations__conversation_id__character_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/conversations/{conversation_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stream Events */
        get: operations["stream_events_api_v1_agent_conversations__conversation_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Message */
        post: operations["post_message_api_v1_agent_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/index/rebuild": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Index Rebuild
         * @description Re-mark every template so the next drain rewrites the whole collection.
         *
         *     This does not delete or rebuild the collection: it is the explicit entry
         *     point for "the index may be wrong, re-derive it from the business store".
         */
        post: operations["index_rebuild_api_v1_agent_index_rebuild_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/index/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Index Status
         * @description Is semantic search usable, and is the template collection current?
         *
         *     The sync half reports the dirty count and the last failure, because a
         *     stale template collection is invisible to the caller otherwise: a search
         *     would simply not return the template they just created.
         */
        get: operations["index_status_api_v1_agent_index_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/index/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Index Sync Now
         * @description Drain the template queue now. The explicit "make it current" action.
         */
        post: operations["index_sync_now_api_v1_agent_index_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Plan */
        get: operations["read_plan_api_v1_agent_plans__plan_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Revise Plan */
        patch: operations["revise_plan_api_v1_agent_plans__plan_id__patch"];
        trace?: never;
    };
    "/api/v1/agent/plans/{plan_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Plan */
        post: operations["approve_plan_api_v1_agent_plans__plan_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/plans/{plan_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Plan */
        post: operations["cancel_plan_api_v1_agent_plans__plan_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/plans/{plan_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Revisions */
        get: operations["read_revisions_api_v1_agent_plans__plan_id__revisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/runs/{run_id}/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Stop Run */
        post: operations["stop_run_api_v1_agent_runs__run_id__stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Settings */
        get: operations["read_settings_api_v1_agent_settings_get"];
        /** Write Settings */
        put: operations["write_settings_api_v1_agent_settings_put"];
        post?: never;
        /** Delete Settings */
        delete: operations["delete_settings_api_v1_agent_settings_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/settings/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read Models */
        post: operations["read_models_api_v1_agent_settings_models_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/settings/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Test */
        post: operations["post_test_api_v1_agent_settings_test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/workbench-changes/{change_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Workbench Change */
        post: operations["approve_workbench_change_api_v1_agent_workbench_changes__change_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent/workbench-changes/{change_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Workbench Change */
        post: operations["cancel_workbench_change_api_v1_agent_workbench_changes__change_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Approvals */
        get: operations["approvals_api_v1_approvals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assets */
        get: operations["assets_api_v1_assets_get"];
        put?: never;
        /** Upload Asset */
        post: operations["upload_asset_api_v1_assets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assets/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Asset */
        get: operations["asset_api_v1_assets__id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assets/{id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve */
        post: operations["approve_api_v1_assets__id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assets/{id}/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Asset File */
        get: operations["asset_file_api_v1_assets__id__file_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assets/{id}/thumbnail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Asset Thumbnail */
        get: operations["asset_thumbnail_api_v1_assets__id__thumbnail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Characters */
        get: operations["characters_api_v1_characters_get"];
        put?: never;
        /** Create Character */
        post: operations["create_character_api_v1_characters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/characters/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Character */
        get: operations["character_api_v1_characters__id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Jobs */
        get: operations["jobs_api_v1_jobs_get"];
        put?: never;
        /** Create Job */
        post: operations["create_job_api_v1_jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Job */
        get: operations["job_api_v1_jobs__id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_api_v1_jobs__id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}/record": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation Record */
        get: operations["generation_record_api_v1_jobs__id__record_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry */
        post: operations["retry_api_v1_jobs__id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Events */
        get: operations["events_api_v1_jobs_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/poses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Poses */
        get: operations["list_poses_api_v1_poses_get"];
        put?: never;
        /** Poses */
        post: operations["poses_api_v1_poses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/capabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Capabilities */
        get: operations["capabilities_api_v1_production_capabilities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/characters/{character_id}/assets/{asset_id}/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Review */
        put: operations["review_api_v1_production_characters__character_id__assets__asset_id__review_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/characters/{character_id}/batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit Batch */
        post: operations["submit_batch_api_v1_production_characters__character_id__batches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/characters/{character_id}/manifest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Manifest */
        get: operations["manifest_api_v1_production_characters__character_id__manifest_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/characters/{character_id}/outfits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Outfit */
        post: operations["create_outfit_api_v1_production_characters__character_id__outfits_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/characters/{character_id}/selection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Selection */
        get: operations["read_selection_api_v1_production_characters__character_id__selection_get"];
        /** Update Selection */
        put: operations["update_selection_api_v1_production_characters__character_id__selection_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/pose-presets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Presets */
        get: operations["list_presets_api_v1_production_pose_presets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/pose-presets/{index}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Save Preset */
        post: operations["save_preset_api_v1_production_pose_presets__index__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/pose-presets/{index}/image": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preset Image */
        get: operations["preset_image_api_v1_production_pose_presets__index__image_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/production/snapshot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Snapshot */
        get: operations["snapshot_api_v1_production_snapshot_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Prompt Settings */
        get: operations["read_prompt_settings_api_v1_prompt_settings_get"];
        /** Write Prompt Settings */
        put: operations["write_prompt_settings_api_v1_prompt_settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Templates */
        get: operations["list_templates_api_v1_prompt_templates_get"];
        put?: never;
        /** Create */
        post: operations["create_api_v1_prompt_templates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_prompt_templates__id__get"];
        /** Edit */
        put: operations["edit_api_v1_prompt_templates__id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/{id}/image": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preview Image */
        get: operations["preview_image_api_v1_prompt_templates__id__image_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export */
        get: operations["export_api_v1_prompt_templates_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload */
        post: operations["upload_api_v1_prompt_templates_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/instantiate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Instantiate */
        post: operations["instantiate_api_v1_prompt_templates_instantiate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prompt-templates/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview */
        post: operations["preview_api_v1_prompt_templates_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/scene-specs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Scene Specs */
        post: operations["scene_specs_api_v1_scene_specs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/scene-specs/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Spec */
        get: operations["get_spec_api_v1_scene_specs__id__get"];
        /** Revise Spec */
        put: operations["revise_spec_api_v1_scene_specs__id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Approval */
        Approval: {
            /** Character Id */
            character_id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "character" | "outfit" | "pose";
            /**
             * Note
             * @default
             */
            note?: string;
            /** Outfit Id */
            outfit_id?: string | null;
        };
        /** ApprovalRecord */
        ApprovalRecord: {
            /** Asset Id */
            asset_id: string;
            /** Character Id */
            character_id: string;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "character" | "outfit" | "pose";
            /** Outfit Id */
            outfit_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** ApproveBody */
        ApproveBody: {
            /**
             * Content Hash
             * @default
             */
            content_hash?: string;
            /** Revision */
            revision: number;
            /** Selection Revision */
            selection_revision?: number | null;
        };
        /** BatchRequest */
        BatchRequest: {
            /** Candidates */
            candidates: components["schemas"]["Candidate"][];
            /** Canvas Preset */
            canvas_preset?: string | null;
            /** Expected Revision */
            expected_revision: number;
            /** Idempotency Key */
            idempotency_key: string;
            /** Retry Of */
            retry_of?: string | null;
            /**
             * Role
             * @enum {string}
             */
            role: "identity" | "outfit" | "pose" | "expression" | "matte";
        };
        /** Body_upload_api_v1_prompt_templates_import_post */
        Body_upload_api_v1_prompt_templates_import_post: {
            /** File */
            file: string;
        };
        /** Body_upload_asset_api_v1_assets_post */
        Body_upload_asset_api_v1_assets_post: {
            /** File */
            file: string;
            /**
             * Role
             * @default reference
             */
            role?: string;
        };
        /** Candidate */
        Candidate: {
            /** Asset Id */
            asset_id?: string | null;
            /**
             * Expression
             * @default
             */
            expression?: string;
            /** Face Region */
            face_region?: [
                number,
                number,
                number,
                number
            ] | null;
            /** Outfit Id */
            outfit_id?: string | null;
            /** Pose Id */
            pose_id?: string | null;
            /**
             * Seed
             * @default 9527
             */
            seed?: number;
        };
        /** Capabilities */
        Capabilities: {
            /** Batches */
            batches: boolean;
            /** Generation Online */
            generation_online: boolean;
            /** Outfit Versions */
            outfit_versions: boolean;
            /** Pose Input */
            pose_input: string;
            /** Selection */
            selection: boolean;
        };
        /** Character */
        Character: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Fixed Tags */
            fixed_tags: string[];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Outfits */
            outfits?: components["schemas"]["Outfit"][];
            prompt_sections?: components["schemas"]["CharacterPromptSections"] | null;
        };
        /** CharacterOutfit */
        CharacterOutfit: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Id */
            id: string;
            /** Tags */
            tags: string[];
        } & {
            [key: string]: unknown;
        };
        /**
         * CharacterPromptSections
         * @description Semantic identity buckets used by the ordered Anima compiler.
         *
         *     ``fixed_tags`` stays as the compatibility snapshot. New character records
         *     also preserve these buckets so the prompt compiler never has to guess
         *     whether an appearance tag is a character or a series.
         */
        CharacterPromptSections: {
            /** Character */
            character?: string[];
            /** General */
            general?: string[];
            /** Series */
            series?: string[];
        };
        /** CharacterRecord */
        CharacterRecord: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Fixed Tags */
            fixed_tags: string[];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Outfits */
            outfits: components["schemas"]["CharacterOutfit"][];
        } & {
            [key: string]: unknown;
        };
        /** ConversationBody */
        ConversationBody: {
            /** Character Id */
            character_id?: string | null;
            /**
             * Title
             * @default
             */
            title?: string;
        };
        /** DeliveryInfo */
        DeliveryInfo: {
            /** Attempts */
            attempts: number;
            /** Generation */
            generation: number;
            /** Received */
            received: boolean;
            /** Request Id */
            request_id: string;
            /** Retryable */
            retryable: boolean;
        };
        /** Health */
        Health: {
            /** Broker Connected */
            broker_connected?: boolean | null;
            /**
             * Execution Mode
             * @default local
             * @enum {string}
             */
            execution_mode?: "local" | "rabbitmq";
            /**
             * Outbox Pending
             * @default 0
             */
            outbox_pending?: number;
            /**
             * Status
             * @constant
             */
            status: "ok";
            /** Worker Alive */
            worker_alive: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JobBody */
        JobBody: {
            /** Reference Asset Id */
            reference_asset_id?: string | null;
            /** Scene Spec Id */
            scene_spec_id: string;
        } & {
            [key: string]: unknown;
        };
        /** JobProgress */
        JobProgress: {
            /** Completed */
            completed?: boolean | null;
            data?: components["schemas"]["ProgressValue"] | null;
            /** Max */
            max?: number | null;
            /** Type */
            type?: string | null;
            /** Value */
            value?: number | null;
        } & {
            [key: string]: unknown;
        };
        /** JobRecord */
        JobRecord: {
            body: components["schemas"]["JobBody"];
            /** Created */
            created: number;
            delivery?: components["schemas"]["DeliveryInfo"] | null;
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /** Outputs */
            outputs: string[];
            progress?: components["schemas"]["JobProgress"] | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "submitting" | "running" | "recovering" | "submission_uncertain" | "succeeded" | "failed" | "needs_correction" | "cancelled";
        } & {
            [key: string]: unknown;
        };
        /** JobRequest */
        JobRequest: {
            /** Face Region */
            face_region?: [
                number,
                number,
                number,
                number
            ] | null;
            /** Idempotency Key */
            idempotency_key: string;
            /** Mask Asset Id */
            mask_asset_id?: string | null;
            /** Pose Asset Id */
            pose_asset_id?: string | null;
            /** Reference Asset Id */
            reference_asset_id?: string | null;
            /** Scene Spec Id */
            scene_spec_id: string;
            /**
             * Seed
             * @default 9527
             */
            seed?: number;
        };
        /** MessageBody */
        MessageBody: {
            context: components["schemas"]["WorkbenchContext"];
            /** Idempotency Key */
            idempotency_key?: string | null;
            /** Text */
            text: string;
        };
        /** Outfit */
        Outfit: {
            /** Caption En */
            caption_en?: string[];
            /**
             * Description
             * @default
             */
            description?: string;
            /** Excluded Tags */
            excluded_tags?: string[];
            /** Id */
            id: string;
            /** Tags */
            tags: string[];
        };
        /** OutfitVersion */
        OutfitVersion: {
            /** Caption En */
            caption_en?: string[];
            /**
             * Description
             * @default
             */
            description?: string;
            /** Excluded Tags */
            excluded_tags?: string[];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id?: string | null;
            /** Tags */
            tags: string[];
        };
        /** OutfitVersionRecord */
        OutfitVersionRecord: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id?: string | null;
            /** Tags */
            tags: string[];
        } & {
            [key: string]: unknown;
        };
        /** PoseRecord */
        PoseRecord: {
            /** Id */
            id: string;
            /**
             * Lighting Prompt
             * @default
             */
            lighting_prompt?: string;
            /** Preset Id */
            preset_id?: number | null;
            /** Render Asset Id */
            render_asset_id: string;
        } & {
            [key: string]: unknown;
        };
        /** PoseState */
        PoseState: {
            /**
             * Lighting Prompt
             * @default
             */
            lighting_prompt?: string;
            /** Render Asset Id */
            render_asset_id: string;
            /** State */
            state: {
                [key: string]: unknown;
            };
        };
        /** ProductionAsset */
        ProductionAsset: {
            /** Download Url */
            download_url: string;
            /** Height */
            height?: number | null;
            /** Id */
            id: string;
            /** Job Id */
            job_id?: string | null;
            /** Mode */
            mode?: string | null;
            /** Parent Asset Id */
            parent_asset_id?: string | null;
            /** Role */
            role: string;
            spec: components["schemas"]["ProductionSpec"];
            /** Width */
            width?: number | null;
        } & {
            [key: string]: unknown;
        };
        /** ProductionBatch */
        ProductionBatch: {
            /** Character Id */
            character_id: string;
            /** Created */
            created: number;
            /** Id */
            id: string;
            /** Job Ids */
            job_ids: string[];
            request: components["schemas"]["BatchRequest"];
            /** Source Asset Id */
            source_asset_id: string | null;
        } & {
            [key: string]: unknown;
        };
        /** ProductionJob */
        ProductionJob: {
            body: components["schemas"]["JobBody"];
            /** Created */
            created: number;
            delivery?: components["schemas"]["DeliveryInfo"] | null;
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /** Outputs */
            outputs: string[];
            progress?: components["schemas"]["JobProgress"] | null;
            spec: components["schemas"]["ProductionSpec"];
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "submitting" | "running" | "recovering" | "submission_uncertain" | "succeeded" | "failed" | "needs_correction" | "cancelled";
        } & {
            [key: string]: unknown;
        };
        /** ProductionPreset */
        ProductionPreset: {
            /** Format */
            format: string;
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Preview Url */
            preview_url: string;
            /** Revision */
            revision: string;
            /** Source */
            source: string;
        };
        /** ProductionSelection */
        ProductionSelection: {
            /** Character Id */
            character_id: string;
            /** Identity Asset Id */
            identity_asset_id: string | null;
            /** Outfit Asset Id */
            outfit_asset_id: string | null;
            /** Outfit Id */
            outfit_id: string | null;
            /** Pose Asset Id */
            pose_asset_id: string | null;
            /** Revision */
            revision: number;
        } & {
            [key: string]: unknown;
        };
        /** ProductionSnapshot */
        ProductionSnapshot: {
            /** Approvals */
            approvals: components["schemas"]["ApprovalRecord"][];
            /** Assets */
            assets: components["schemas"]["ProductionAsset"][];
            /** Batches */
            batches: components["schemas"]["ProductionBatch"][];
            /** Characters */
            characters: components["schemas"]["CharacterRecord"][];
            /** Jobs */
            jobs: components["schemas"]["ProductionJob"][];
            /** Outfit Versions */
            outfit_versions: components["schemas"]["OutfitVersionRecord"][];
            /** Poses */
            poses: components["schemas"]["PoseRecord"][];
            /** Reviews */
            reviews: components["schemas"]["ReviewRecord"][];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Selections */
            selections: components["schemas"]["ProductionSelection"][];
        };
        /** ProductionSpec */
        ProductionSpec: {
            /**
             * Action
             * @default
             */
            action?: string;
            /** Asset Type */
            asset_type?: string | null;
            /** Character Id */
            character_id?: string | null;
            /**
             * Expression
             * @default
             */
            expression?: string;
            /** Outfit Id */
            outfit_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** ProgressValue */
        ProgressValue: {
            /** Max */
            max?: number | null;
            /** Value */
            value?: number | null;
        } & {
            [key: string]: unknown;
        };
        /** PromptSettings */
        PromptSettings: {
            /** Artist Style */
            artist_style: string;
            /** Content Hash */
            content_hash: string;
            /** Fixed Negative */
            fixed_negative: string;
            /** Fixed Positive */
            fixed_positive: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Source
             * @enum {string}
             */
            source: "default" | "saved";
            /** Updated At */
            updated_at?: number | null;
        };
        /** PromptSettingsUpdate */
        PromptSettingsUpdate: {
            /**
             * Artist Style
             * @default @rella
             */
            artist_style?: string;
            /**
             * Fixed Negative
             * @default score_1, score_2, score_3, blurry, worst quality, low quality, jpeg artifacts, signature, watermark, username, error, deformed hands, bad anatomy, extra limbs, poorly drawn hands, poorly drawn face, mutation, deformed, extra eyes, extra arms, extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed, bad proportions, missing arms, missing legs, extra digit, fewer digits, cropped, normal quality, monochrome, greyscale, lineart
             */
            fixed_negative?: string;
            /**
             * Fixed Positive
             * @default masterpiece, very aesthetic, best quality, score_9, score_8, score_7, year 2025, official_art
             */
            fixed_positive?: string;
        };
        /** PromptTemplate */
        PromptTemplate: {
            /** Caption En */
            caption_en?: string[];
            /** Categories */
            categories?: string[];
            /**
             * Description
             * @default
             */
            description?: string;
            /** Excluded Tags */
            excluded_tags?: string[];
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "character" | "outfit";
            /** Name */
            name: string;
            /**
             * Source
             * @default user
             */
            source?: string;
            /**
             * Source Key
             * @default
             */
            source_key?: string;
            /**
             * Source Revision
             * @default
             */
            source_revision?: string;
            /** Tags */
            tags?: string[];
            /**
             * Trigger
             * @default
             */
            trigger?: string;
        };
        /** RetryRequest */
        RetryRequest: {
            /** Generation */
            generation: number;
        };
        /** ReviewRecord */
        ReviewRecord: {
            /** Asset Id */
            asset_id: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "accepted" | "rejected";
            /**
             * Note
             * @default
             */
            note?: string;
        } & {
            [key: string]: unknown;
        };
        /** ReviewRequest */
        ReviewRequest: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "accepted" | "rejected";
            /** Expected Revision */
            expected_revision: number;
            /**
             * Note
             * @default
             */
            note?: string;
        };
        /** SceneRequest */
        SceneRequest: {
            /**
             * Asset Type
             * @default sprite
             * @enum {string}
             */
            asset_type?: "sprite" | "background" | "outfit" | "pose" | "expression" | "matte" | "free";
            /** Character Id */
            character_id?: string | null;
            manual?: components["schemas"]["SceneSpec"] | null;
            /** Outfit Id */
            outfit_id?: string | null;
            /** Story */
            story?: string | null;
        };
        /** SceneSpec */
        SceneSpec: {
            /**
             * Action
             * @default
             */
            action?: string;
            /**
             * Asset Type
             * @enum {string}
             */
            asset_type: "sprite" | "background" | "outfit" | "pose" | "expression" | "matte" | "free";
            /** Canvas Preset */
            canvas_preset?: string | null;
            /** Character Id */
            character_id?: string | null;
            /**
             * Composition
             * @default
             */
            composition?: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Excluded Tags */
            excluded_tags?: string[];
            /**
             * Expression
             * @default
             */
            expression?: string;
            /** Outfit Id */
            outfit_id?: string | null;
            /** Prompt Captions */
            prompt_captions?: string[];
            /**
             * Scene
             * @default
             */
            scene?: string;
            /** Unresolved */
            unresolved?: string[];
            /** Visual Tags */
            visual_tags?: string[];
        };
        /** SelectionRequest */
        SelectionRequest: {
            /**
             * Approve
             * @default false
             */
            approve?: boolean;
            /** Asset Id */
            asset_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * Stage
             * @enum {string}
             */
            stage: "identity" | "outfit" | "pose";
        };
        /** SettingsBody */
        SettingsBody: {
            /**
             * Api Key
             * @default
             */
            api_key?: string;
            /**
             * Base Url
             * @default
             */
            base_url?: string;
            /**
             * Keep Existing Key
             * @default false
             */
            keep_existing_key?: boolean;
            /**
             * Model
             * @default
             */
            model?: string;
            /**
             * Provider
             * @default custom
             */
            provider?: string;
            /**
             * Remember
             * @default true
             */
            remember?: boolean;
        };
        /** TemplateSelection */
        TemplateSelection: {
            /** Character Id */
            character_id: string;
            /** Character Template Id */
            character_template_id: string;
            /**
             * Include Character Tags
             * @default true
             */
            include_character_tags?: boolean;
            /** Name */
            name?: string | null;
            /** Outfit Template Ids */
            outfit_template_ids?: string[];
        };
        /**
         * UncommittedDraft
         * @description Local, un-submitted workbench state. Never mixed with server truth.
         */
        UncommittedDraft: {
            /**
             * Note
             * @default
             */
            note?: string;
            /** Stage */
            stage: string;
            /** Values */
            values?: {
                [key: string]: unknown;
            };
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** WorkbenchChangeApprovalBody */
        WorkbenchChangeApprovalBody: {
            /** Content Hash */
            content_hash: string;
        };
        /**
         * WorkbenchContext
         * @description What the user is looking at right now, sent with every message.
         */
        WorkbenchContext: {
            /** Candidate Set Id */
            candidate_set_id?: string | null;
            /** Canvas Preset */
            canvas_preset?: string | null;
            /** Character Id */
            character_id?: string | null;
            /**
             * Character Name
             * @default
             */
            character_name?: string;
            /**
             * Interaction Mode
             * @default guided
             * @enum {string}
             */
            interaction_mode?: "guided" | "direct";
            /** Known Character Ids */
            known_character_ids?: string[];
            /** Selected Asset Ids */
            selected_asset_ids?: {
                [key: string]: string | null;
            };
            /** Selected Outfit Id */
            selected_outfit_id?: string | null;
            /**
             * Selection Revision
             * @default 0
             */
            selection_revision?: number;
            /**
             * Stage
             * @default none
             * @enum {string}
             */
            stage?: "none" | "identity" | "outfit" | "pose" | "expression" | "export";
            uncommitted_draft?: components["schemas"]["UncommittedDraft"] | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_conversations_api_v1_agent_conversations_get: {
        parameters: {
            query?: {
                character_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_conversation_api_v1_agent_conversations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_conversation_api_v1_agent_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rebind_character_api_v1_agent_conversations__conversation_id__character_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_events_api_v1_agent_conversations__conversation_id__events_get: {
        parameters: {
            query?: {
                after?: string;
            };
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_message_api_v1_agent_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    index_rebuild_api_v1_agent_index_rebuild_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    index_status_api_v1_agent_index_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    index_sync_now_api_v1_agent_index_sync_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    read_plan_api_v1_agent_plans__plan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revise_plan_api_v1_agent_plans__plan_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_plan_api_v1_agent_plans__plan_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_plan_api_v1_agent_plans__plan_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_revisions_api_v1_agent_plans__plan_id__revisions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stop_run_api_v1_agent_runs__run_id__stop_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_settings_api_v1_agent_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    write_settings_api_v1_agent_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_settings_api_v1_agent_settings_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    read_models_api_v1_agent_settings_models_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    post_test_api_v1_agent_settings_test_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    approve_workbench_change_api_v1_agent_workbench_changes__change_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                change_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkbenchChangeApprovalBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_workbench_change_api_v1_agent_workbench_changes__change_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                change_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approvals_api_v1_approvals_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    assets_api_v1_assets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    upload_asset_api_v1_assets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_asset_api_v1_assets_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    asset_api_v1_assets__id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_api_v1_assets__id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Approval"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    asset_file_api_v1_assets__id__file_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    asset_thumbnail_api_v1_assets__id__thumbnail_get: {
        parameters: {
            query?: {
                size?: "384" | "768" | "1536";
            };
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    characters_api_v1_characters_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterRecord"][];
                };
            };
        };
    };
    create_character_api_v1_characters_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Character"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    character_api_v1_characters__id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    jobs_api_v1_jobs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobRecord"][];
                };
            };
        };
    };
    create_job_api_v1_jobs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JobRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    job_api_v1_jobs__id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_api_v1_jobs__id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generation_record_api_v1_jobs__id__record_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_api_v1_jobs__id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    events_api_v1_jobs_events_get: {
        parameters: {
            query?: {
                after?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_poses_api_v1_poses_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    poses_api_v1_poses_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PoseState"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    capabilities_api_v1_production_capabilities_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Capabilities"];
                };
            };
        };
    };
    review_api_v1_production_characters__character_id__assets__asset_id__review_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_batch_api_v1_production_characters__character_id__batches_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BatchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductionBatch"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    manifest_api_v1_production_characters__character_id__manifest_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_outfit_api_v1_production_characters__character_id__outfits_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutfitVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutfitVersionRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_selection_api_v1_production_characters__character_id__selection_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductionSelection"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_selection_api_v1_production_characters__character_id__selection_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SelectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductionSelection"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_presets_api_v1_production_pose_presets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductionPreset"][];
                };
            };
        };
    };
    save_preset_api_v1_production_pose_presets__index__post: {
        parameters: {
            query?: {
                height?: number | null;
                width?: number | null;
            };
            header?: never;
            path: {
                index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PoseRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preset_image_api_v1_production_pose_presets__index__image_get: {
        parameters: {
            query?: {
                height?: number | null;
                width?: number | null;
            };
            header?: never;
            path: {
                index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    snapshot_api_v1_production_snapshot_get: {
        parameters: {
            query?: {
                character_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductionSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_prompt_settings_api_v1_prompt_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PromptSettings"];
                };
            };
        };
    };
    write_prompt_settings_api_v1_prompt_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PromptSettingsUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PromptSettings"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_templates_api_v1_prompt_templates_get: {
        parameters: {
            query?: {
                category?: string | null;
                kind?: ("character" | "outfit") | null;
                limit?: number;
                offset?: number;
                q?: string;
                source?: ("upstream" | "user") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_api_v1_prompt_templates_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PromptTemplate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_prompt_templates__id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    edit_api_v1_prompt_templates__id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PromptTemplate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_image_api_v1_prompt_templates__id__image_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_api_v1_prompt_templates_export_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    upload_api_v1_prompt_templates_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_api_v1_prompt_templates_import_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    instantiate_api_v1_prompt_templates_instantiate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateSelection"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_api_v1_prompt_templates_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateSelection"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    scene_specs_api_v1_scene_specs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SceneRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_spec_api_v1_scene_specs__id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revise_spec_api_v1_scene_specs__id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SceneSpec"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
