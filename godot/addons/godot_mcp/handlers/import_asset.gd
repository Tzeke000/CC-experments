@tool
class_name MCPImportAssetHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
## Domain handler: external asset import and material assembly (issue #108).
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_import_asset"] = _cmd_import_asset
	handlers["cmd_create_material_from_textures"] = _cmd_create_material_from_textures
	handlers["cmd_get_import_status"] = _cmd_get_import_status
	handlers["cmd_reimport_assets"] = _cmd_reimport_assets
	handlers["cmd_diagnose_import"] = _cmd_diagnose_import


# -- helpers -----------------------------------------------------------------

func _is_number(value: String) -> bool:
	return value.is_valid_float()


func _copy_file(source: String, target: String, overwrite: bool) -> int:
	if FileAccess.file_exists(target) and not overwrite:
		return ERR_ALREADY_EXISTS
	var src := FileAccess.open(source, FileAccess.READ)
	if src == null:
		return FileAccess.get_open_error()
	var dst := FileAccess.open(target, FileAccess.WRITE)
	if dst == null:
		src.close()
		return FileAccess.get_open_error()
	const CHUNK := 65536
	var remaining := src.get_length()
	while remaining > 0:
		var read_size := mini(CHUNK, remaining)
		var buf := src.get_buffer(read_size)
		dst.store_buffer(buf)
		remaining -= read_size
	src.close()
	dst.close()
	return OK


func _detect_type(path: String) -> String:
	var ext := path.get_extension().to_lower()
	match ext:
		"png", "jpg", "jpeg", "webp", "svg":
			return "Texture2D"
		# .blend imports via Blender→glTF in the editor (PackedScene). Prefer
		# committing .glb/.gltf so teammates need not install Blender.
		"glb", "gltf", "fbx", "blend":
			return "PackedScene"
		"obj":
			return "Mesh"
		"wav":
			return "AudioStreamWAV"
		"ogg":
			return "AudioStreamOggVorbis"
		"mp3":
			return "AudioStreamMP3"
		"tres", "res":
			return "Resource"
		"tscn", "scn":
			return "PackedScene"
		"gd":
			return "GDScript"
		"cs":
			return "CSharpScript"
		"gdshader":
			return "Shader"
	return ""


## Godot built-in import name suffixes (docs: node type customization).
const _GODOT_SUFFIXES := [
	"-colonly", "-convcolonly", "-convcol", "-col", "-noimp", "-navmesh",
	"-occonly", "-occ", "-rigid", "-vehicle", "-wheel", "-alpha", "-vcol",
]


func _suffix_hits(name: String) -> Array:
	var hits: Array = []
	var lower := name.to_lower()
	for suffix in _GODOT_SUFFIXES:
		if lower.ends_with(suffix) or lower.ends_with(suffix.replace("-", "_")) \
				or lower.ends_with(suffix.replace("-", "$")):
			hits.append(suffix)
	# Animation loop tokens are prefix/suffix without requiring a hyphen.
	if lower.begins_with("loop") or lower.ends_with("loop") \
			or lower.begins_with("cycle") or lower.ends_with("cycle"):
		hits.append("loop/cycle")
	return hits


func _gltf_pipeline_enabled() -> bool:
	# EditorInterface.is_plugin_enabled takes the addon folder name (Godot 4.x).
	if EditorInterface.has_method("is_plugin_enabled"):
		if EditorInterface.is_plugin_enabled("gltf_pipeline"):
			return true
	# Fallback: enabled plugins list in project settings.
	var enabled: PackedStringArray = ProjectSettings.get_setting(
		"editor_plugins/enabled", PackedStringArray()
	)
	for entry in enabled:
		var s := str(entry)
		if s.contains("gltf_pipeline"):
			return true
	return false


func _read_gltf_json(abs_path: String) -> Variant:
	if not FileAccess.file_exists(abs_path):
		return null
	var f := FileAccess.open(abs_path, FileAccess.READ)
	if f == null:
		return null
	var text := f.get_as_text()
	f.close()
	var parsed: Variant = JSON.parse_string(text)
	return parsed


func _summarize_gltf_extras(doc: Dictionary) -> Dictionary:
	var nodes_with_extras: Array = []
	var collision_extras: Array = []
	var suffix_hits: Array = []
	var name_overrides: Array = []
	var nodes: Array = doc.get("nodes", [])
	for node in nodes:
		if typeof(node) != TYPE_DICTIONARY:
			continue
		var n: Dictionary = node
		var name := str(n.get("name", ""))
		for hit in _suffix_hits(name):
			suffix_hits.append({"node": name, "suffix": hit})
		if not n.has("extras"):
			continue
		var extras: Variant = n["extras"]
		if typeof(extras) != TYPE_DICTIONARY:
			continue
		var ex: Dictionary = extras
		nodes_with_extras.append(name if not name.is_empty() else "(unnamed)")
		if ex.has("collision"):
			collision_extras.append({"node": name, "collision": str(ex["collision"])})
		if ex.has("name_override"):
			name_overrides.append({"node": name, "name_override": str(ex["name_override"])})
	return {
		"nodes_with_extras": nodes_with_extras,
		"collision_extras": collision_extras,
		"name_overrides": name_overrides,
		"suffix_hits": suffix_hits,
		"node_count": nodes.size(),
	}


# -- handlers ----------------------------------------------------------------

## Ensure a filesystem scan will import a freshly copied file (issue #628).
##
## Godot coalesces scan() calls: one issued while another scan is already in
## flight is dropped, so a new file can sit unimported indefinitely. Start a scan
## now when none is running and return true; if a scan is in flight, return false
## so the caller can defer (the plugin re-issues one when it finishes). `fs` is
## duck-typed ({is_scanning, scan}) so this is verifiable headlessly.
static func ensure_scan(fs: Object) -> bool:
	if fs == null or fs.is_scanning():
		return false
	fs.scan()
	return true


func _cmd_import_asset(params: Dictionary) -> Dictionary:
	var source := str(params.get("source", ""))
	var target_path := str(params.get("target_path", ""))
	var overwrite := bool(params.get("overwrite", false))
	var import_settings: Dictionary = params.get("import_settings", {})

	if not target_path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "target_path must start with res://.")

	var before_state := MCPReceipt.file_state(target_path)
	var abs_target := ProjectSettings.globalize_path(target_path)
	var abs_source := source
	if source.begins_with("res://"):
		abs_source = ProjectSettings.globalize_path(source)

	var base_dir := abs_target.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)

	var err := _copy_file(abs_source, abs_target, overwrite)
	if err == ERR_ALREADY_EXISTS:
		return _router._fail("PRECONDITION_FAILED", "Target already exists. Pass overwrite=true to replace.", "overwrite")
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to copy file (error %d)." % err)

	# #628: start a scan now if none is in flight; otherwise defer — the plugin
	# re-issues one when the in-flight scan finishes, so the copied file imports
	# instead of being silently missed (Godot coalesces scan() calls).
	var fs := EditorInterface.get_resource_filesystem()
	var scan_deferred := not ensure_scan(fs)
	if scan_deferred:
		_router.pending_rescan = true

	var detected_type := _detect_type(target_path)
	if import_settings.has("type"):
		detected_type = str(import_settings["type"])

	# #418: an imported .wav's loop config is an import OPTION (the .import sidecar's
	# params), not an editable .tres property — AudioStreamWAV.loop_mode is read-only
	# on the imported artifact. Patch the sidecar + reimport so the loop config lands
	# in the imported artifact.
	var loop_applied := false
	if detected_type == "AudioStreamWAV" and import_settings.has("loop_mode"):
		loop_applied = _set_wav_loop(target_path, import_settings)

	if not FileAccess.file_exists(target_path):
		return _router._ok({
			"imported": false,
			"target_path": target_path,
			"detected_type": detected_type,
			"loop_applied": loop_applied,
			"scan_deferred": scan_deferred,
			"hint": "The import did not leave a file at the target path.",
			"receipt": MCPReceipt.make("noop", []),
		})
	return _router._ok({
		"imported": true,
		"target_path": target_path,
		"detected_type": detected_type,
		"loop_applied": loop_applied,
		"scan_deferred": scan_deferred,
		"receipt": MCPReceipt.make(
			"updated" if before_state["exists"] else "created",
			[MCPReceipt.change(target_path, "write", before_state, MCPReceipt.file_state(target_path))],
		),
	})


## Patch the .import sidecar's edit/loop_* params and reimport so the imported
## AudioStreamWAV carries them (issue #418). The scan the import just started
## produces the sidecar asynchronously — this handler cannot block its own main
## thread, so when the sidecar is not there yet the loop params are written into
## a fresh sidecar based on the engine's WAV defaults (ResourceImporterWAV's
## params, minus the loop keys being set) and a reimport is queued; the importer
## applies the params when the scan reaches the file. `loop_applied` reports
## whether the params were written this call.
func _set_wav_loop(target_path: String, import_settings: Dictionary) -> bool:
	var sidecar := target_path + ".import"
	var cfg := ConfigFile.new()
	if FileAccess.file_exists(ProjectSettings.globalize_path(sidecar)):
		if cfg.load(sidecar) != OK:
			return false
	var loop_mode := int(import_settings["loop_mode"])
	cfg.set_value("params", "edit/loop_mode", loop_mode)
	if import_settings.has("loop_begin"):
		cfg.set_value("params", "edit/loop_begin", int(import_settings["loop_begin"]))
	if import_settings.has("loop_end"):
		cfg.set_value("params", "edit/loop_end", int(import_settings["loop_end"]))
	# The sidecar needs the importer identity + deps too — when it does not exist
	# yet, seed it from what a first import of this file will write (importer
	# name + destination are stable for AudioStreamWAV).
	if cfg.get_value("remap", "importer", "") == "":
		cfg.set_value("remap", "importer", "wav")
		cfg.set_value("remap", "type", "AudioStreamWAV")
		cfg.set_value("deps", "", "md5")
	cfg.save(sidecar)
	var fs := EditorInterface.get_resource_filesystem()
	var files := PackedStringArray([target_path])
	fs.reimport_files(files)
	return true


func _cmd_create_material_from_textures(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var channels: Dictionary = {
		"albedo": str(params.get("albedo", "")),
		"normal": str(params.get("normal", "")),
		"roughness": str(params.get("roughness", "")),
		"metallic": str(params.get("metallic", "")),
		"ao": str(params.get("ao", "")),
		"emission": str(params.get("emission", "")),
	}
	# #419: metallic/roughness/emission_enabled are scalar floats on
	# StandardMaterial3D — a numeric string sets the property directly instead of
	# being mistaken for a texture path that aborts the whole material.
	var emission_enabled := str(params.get("emission_enabled", ""))
	var emission_requested: bool = not channels["emission"].is_empty()

	var material: StandardMaterial3D = StandardMaterial3D.new()
	var channels_set: Array = []

	for channel in channels:
		var value: String = channels[channel]
		if value.is_empty():
			continue
		if _is_number(value):
			var scalar := value.to_float()
			match channel:
				"roughness":
					material.roughness = scalar
				"metallic":
					material.metallic = scalar
				_:
					return _router._fail("VALIDATION_ERROR", "Channel '%s' is a texture; a numeric value is not valid there." % channel)
			channels_set.append(channel + ":scalar")
			continue
		if not ResourceLoader.exists(value):
			return _router._fail("RESOURCE_NOT_FOUND", "Texture not found for '%s': '%s'." % [channel, value])
		var tex: Texture2D = ResourceLoader.load(value)
		if tex == null:
			return _router._fail("INTERNAL_ERROR", "Failed to load texture '%s' for '%s'." % [value, channel])
		match channel:
			"albedo":
				material.albedo_texture = tex
			"normal":
				material.normal_texture = tex
			"roughness":
				material.roughness_texture = tex
			"metallic":
				material.metallic_texture = tex
			"ao":
				material.ao_texture = tex
			"emission":
				material.emission_texture = tex
		channels_set.append(channel)

	# #428: an emission texture with emission_enabled=false + black color is a
	# half-set that renders non-emissive no matter the texture. Any emission
	# request (texture or enabled-scalar) turns emission ON; texture-without-
	# explicit-scalar defaults the color to white. The caller can tune
	# color/energy afterwards via set_resource_property.
	if emission_requested or emission_enabled.is_valid_float():
		material.emission_enabled = true
		material.emission = Color(1.0, 1.0, 1.0)
		channels_set.append("emission_enabled:scalar")
		if not emission_enabled.is_empty() and emission_enabled.is_valid_float():
			# Explicit "0"/"false"-valued scalar wins: the caller explicitly
			# disabled emission (e.g. they intend to wire it up manually later).
			material.emission_enabled = emission_enabled.to_float() > 0.5

	if path.is_empty():
		path = "res://materials/generated_%s.tres" % str(randi()).sha256_text().substr(0, 8)
	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "path must start with res://.")

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(base_dir)):
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(base_dir))

	var err := ResourceSaver.save(material, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save material to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)

	return _router._ok({
		"material_path": path,
		"created": true,
		"channels_set": channels_set,
	})


func _cmd_get_import_status(params: Dictionary) -> Dictionary:
	var target_path := str(params.get("target_path", ""))
	if not target_path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "target_path must start with res://.")

	var import_file := ProjectSettings.globalize_path(target_path + ".import")
	var imported := FileAccess.file_exists(import_file)
	var last_modified: String = ""
	var type: String = ""

	if imported:
		var cfg := ConfigFile.new()
		var err := cfg.load(import_file)
		if err == OK:
			type = cfg.get_value("remap", "type", "")
		if type.is_empty():
			type = _detect_type(target_path)
		var mtime := FileAccess.get_modified_time(import_file)
		last_modified = Time.get_datetime_string_from_unix_time(mtime)
	else:
		# Fallback: the file may not have an .import sidecar yet; report
		# whether the actual resource file exists and the extension type.
		imported = ResourceLoader.exists(target_path)
		if imported:
			type = _detect_type(target_path)

	return _router._ok({
		"imported": imported,
		"last_modified": last_modified if not last_modified.is_empty() else null,
		"type": type if not type.is_empty() else null,
		# #459/#453: while the editor's filesystem scan is in flight (an import just
		# triggered one) the status is provisional — say so instead of reporting
		# `imported: false` forever.
		"scanning": EditorInterface.get_resource_filesystem().is_scanning(),
		"reason": "rescan_in_flight" if EditorInterface.get_resource_filesystem().is_scanning() and not imported else null,
	})


func _cmd_reimport_assets(params: Dictionary) -> Dictionary:
	## Force EditorFileSystem.reimport_files on one or more res:// paths so an
	## agent can refresh Blender→Godot glTF after an in-place overwrite without
	## guessing at rescan_filesystem side effects.
	var raw_paths: Variant = params.get("paths", [])
	if typeof(raw_paths) != TYPE_ARRAY and typeof(raw_paths) != TYPE_PACKED_STRING_ARRAY:
		return _router._fail("VALIDATION_ERROR", "'paths' must be an array of res:// paths.")
	if raw_paths.is_empty():
		return _router._fail("VALIDATION_ERROR", "'paths' must contain at least one res:// path.")

	var files := PackedStringArray()
	var missing: Array = []
	for item in raw_paths:
		var path := str(item)
		if not path.begins_with("res://"):
			return _router._fail("VALIDATION_ERROR", "Each path must start with res:// (got '%s')." % path)
		var abs := ProjectSettings.globalize_path(path)
		if not FileAccess.file_exists(abs):
			missing.append(path)
			continue
		files.append(path)

	if files.is_empty():
		return _router._fail(
			"RESOURCE_NOT_FOUND",
			"None of the requested paths exist on disk. Check paths[] and res:// mapping.",
		)

	var fs := EditorInterface.get_resource_filesystem()
	fs.reimport_files(files)
	# Also nudge a scan so brand-new sidecars / deps settle (#628 coalescing).
	var scan_deferred := not ensure_scan(fs)
	if scan_deferred:
		_router.pending_rescan = true

	return _router._ok({
		"reimported": true,
		"paths": Array(files),
		"missing": missing,
		"scan_deferred": scan_deferred,
		"scanning": fs.is_scanning(),
		"hint": (
			"Reimport queued. Poll godot_asset_import_get_status / diagnose_import; "
			+ "do not claim success without scene-tree evidence."
		),
	})


func _cmd_diagnose_import(params: Dictionary) -> Dictionary:
	## Agent-facing import diagnose loop: sidecar honesty, scan state, glTF
	## extras/suffix summary, and whether MIT gltf_pipeline is enabled.
	var target_path := str(params.get("target_path", ""))
	if not target_path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "target_path must start with res://.")

	var issues: Array = []
	var hints: Array = []
	var abs_path := ProjectSettings.globalize_path(target_path)
	var file_exists := FileAccess.file_exists(abs_path)
	if not file_exists:
		issues.append("FILE_MISSING")
		hints.append("Place the asset under the project (e.g. res://art/) or call godot_asset_import_asset first.")

	var sidecar_path := ProjectSettings.globalize_path(target_path + ".import")
	var sidecar_present := FileAccess.file_exists(sidecar_path)
	var remap_type := ""
	var importer := ""
	if sidecar_present:
		var cfg := ConfigFile.new()
		if cfg.load(target_path + ".import") == OK:
			remap_type = str(cfg.get_value("remap", "type", ""))
			importer = str(cfg.get_value("remap", "importer", ""))
	elif file_exists:
		issues.append("SIDECAR_MISSING")
		hints.append("Editor has not finished importing — wait_for_scan / get_import_status, or reimport.")

	var fs := EditorInterface.get_resource_filesystem()
	var scanning := fs.is_scanning()
	if scanning:
		issues.append("RESCAN_IN_FLIGHT")
		hints.append("Filesystem scan still running; status is provisional.")

	var ext := target_path.get_extension().to_lower()
	var detected_type := _detect_type(target_path)
	if ext == "blend":
		hints.append(
			"Prefer committing .glb/.gltf. .blend requires Blender ≥3.5 on PATH "
			+ "(Editor Settings → Filesystem → Import → Blender Path)."
		)

	var gltf_summary: Dictionary = {}
	var extras_compatible := false
	if ext == "gltf" and file_exists:
		var doc: Variant = _read_gltf_json(abs_path)
		if typeof(doc) == TYPE_DICTIONARY:
			gltf_summary = _summarize_gltf_extras(doc)
			extras_compatible = not gltf_summary.get("collision_extras", []).is_empty() \
				or not gltf_summary.get("name_overrides", []).is_empty()
			if extras_compatible and not _gltf_pipeline_enabled():
				issues.append("PIPELINE_PLUGIN_OFF")
				hints.append(
					"glTF carries Pipeline extras but addons/gltf_pipeline is not enabled — "
					+ "enable the MIT plugin or collisions/name_override will not apply."
				)
		else:
			issues.append("GLTF_PARSE_FAILED")
			hints.append("Could not parse .gltf JSON; check the file is valid glTF 2.0.")
	elif ext == "glb" and file_exists:
		hints.append(
			"Binary .glb: extras not parsed here. Re-export as glTF Separate for diagnose, "
			+ "or open the imported scene and inspect the tree."
		)

	var pipeline_enabled := _gltf_pipeline_enabled()
	var ready := (
		file_exists
		and sidecar_present
		and not scanning
		and not issues.has("PIPELINE_PLUGIN_OFF")
		and not issues.has("GLTF_PARSE_FAILED")
	)

	return _router._ok({
		"target_path": target_path,
		"file_exists": file_exists,
		"sidecar_present": sidecar_present,
		"scanning": scanning,
		"detected_type": detected_type if not detected_type.is_empty() else null,
		"remap_type": remap_type if not remap_type.is_empty() else null,
		"importer": importer if not importer.is_empty() else null,
		"gltf_pipeline_enabled": pipeline_enabled,
		"gltf_summary": gltf_summary,
		"issues": issues,
		"hints": hints,
		"ready": ready,
		"reason": "rescan_in_flight" if scanning and not sidecar_present else null,
		"hint": (
			"Import looks ready — still verify with godot_inspection_get_scene_tree."
			if ready
			else "Import not ready; resolve issues[] / hints[] before claiming success."
		),
	})
