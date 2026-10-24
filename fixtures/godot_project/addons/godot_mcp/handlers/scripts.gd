@tool
class_name MCPScriptHandlers
extends RefCounted
## Domain handler: scripts.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("../scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_script_for_node"] = _cmd_get_script_for_node
	handlers["cmd_get_scan_state"] = _cmd_get_scan_state
	handlers["cmd_list_scripts"] = _cmd_list_scripts
	handlers["cmd_patch_script"] = _cmd_patch_script
	handlers["cmd_read_script"] = _cmd_read_script
	handlers["cmd_write_script"] = _cmd_write_script
	handlers["cmd_build_csharp"] = _cmd_build_csharp


# -- handlers ----------------------------------------------------------------

## #453: is the editor's filesystem scan still in flight? The parse check's
## subprocess reads global_script_class_cache.cfg from disk — the deferred scan
## after a script write (issue #417) must have *flushed*, not merely started,
## for the read to be deterministic. get_parse_errors polls this before it runs.
func _cmd_get_scan_state(_params: Dictionary) -> Dictionary:
	var fs := EditorInterface.get_resource_filesystem()
	return _router._ok({"scanning": fs.is_scanning()})

func _cmd_read_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	# #207 Phase 1: language-aware — .gd (default) and .cs both read.
	if not path.ends_with(".gd") and not path.ends_with(".cs"):
		return _router._fail(
			"VALIDATION_ERROR",
			"script_path must be a .gd or .cs file: '%s'." % path,
		)
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	return _router._ok({"script_path": path, "content": FileAccess.get_file_as_string(path)})



func _cmd_list_scripts(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	# #207 Phase 1: language-aware — "gd" (default) collects .gd, "cs" collects .cs.
	var language := str(params.get("language", "gd"))
	if language != "gd" and language != "cs":
		return _router._fail("VALIDATION_ERROR", "language must be 'gd' or 'cs'.", "language")
	var scripts: Array = []
	_collect_scripts(directory, scripts, language)
	scripts.sort()
	return _router._ok({"directory": directory, "scripts": scripts})



func _cmd_get_script_for_node(params: Dictionary) -> Dictionary:
	var raw := str(params.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	var node: Node
	if raw.is_empty():
		var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
		if selected.is_empty():
			return _router._fail("PRECONDITION_FAILED", "No node_path given and nothing selected.", "node_or_selection")
		node = selected[0]
	else:
		if root == null:
			return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
		if raw.begins_with("/"):
			raw = raw.substr(1)
		if raw.is_empty():
			raw = "."
		node = root.get_node_or_null(NodePath(raw))
		if node == null:
			return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % raw)
	# Always report the resolved scene-relative path so the response is self-describing.
	var resolved := Inspect.relative_path(node, root) if root != null else String(node.name)
	var script: Variant = node.get_script()
	if not (script is Script) or script.resource_path.is_empty():
		return _router._ok({"node_path": resolved, "script_path": null, "content": null})
	return _router._ok({
		"node_path": resolved,
		"script_path": script.resource_path,
		"content": FileAccess.get_file_as_string(script.resource_path),
	})



func _cmd_write_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	# Require a res:// script path (.gd or .cs, #207 Phase 1). Containment against
	# res:// escape is enforced server-side; this is defense-in-depth.
	if not path.begins_with("res://") \
			or (not path.ends_with(".gd") and not path.ends_with(".cs")):
		return _router._fail("VALIDATION_ERROR", "script_path must be a res:// .gd or .cs file.")
	var content := str(params.get("content", ""))
	var before_state := MCPReceipt.file_state(path)
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Write script %s" % path, UndoRedo.MERGE_DISABLE, _router.asset_action_context())
	ur.add_do_method(_router, "_write_file_text", path, content)
	if existed:
		ur.add_undo_method(_router, "_write_file_text", path, old)
	else:
		# Undo a freshly-created script: remove the file and its Godot 4.4+ .uid
		# sidecar so nothing is left orphaned (parity with the shader handler).
		ur.add_undo_method(_router, "_remove_file_with_uid", path)
	ur.commit_action()
	# #424: report what actually happened — an overwrite reads as success
	# (overwrote/previous_existed), never as a no-op ("would_overwrite" is the
	# dry-run probe's phrasing and stays there).
	var landed := FileAccess.get_file_as_string(path)
	if landed != content:
		return _router._ok({
			"script_path": path, "created": false,
			"overwrote": false, "previous_existed": existed,
			"hint": "The editor did not keep the script content.",
			"receipt": MCPReceipt.make("noop", []),
		})
	return _router._ok({
		"script_path": path, "created": not existed,
		"overwrote": existed, "previous_existed": existed,
		"receipt": MCPReceipt.make(
			"created" if not existed else "updated",
			[MCPReceipt.change(path, "write", before_state, MCPReceipt.file_state(path))],
		),
	})



func _cmd_build_csharp(params: Dictionary) -> Dictionary:
	## Making Things / issue #207 Phase 2: run ``dotnet build`` on the project csproj.
	## Prefer the MCP tool (server-side) when available; this path works from the
	## editor alone for dock/script-check flows.
	if not ClassDB.class_exists("CSharpScript"):
		return _router._fail(
			"UNSUPPORTED",
			"C# build requires a Godot .NET/mono editor binary.",
			"csharp_supported",
		)
	var csproj := _router._csproj_path()
	if csproj.is_empty():
		return _router._fail(
			"PRECONDITION_FAILED",
			"No .csproj at res:// root — not a C# Godot project.",
			"csharp_project",
		)
	if not _router._dotnet_cli_available():
		return _router._fail(
			"PRECONDITION_FAILED",
			"dotnet CLI not found on PATH. Install .NET 8 SDK, then retry.",
			"csharp_build",
		)
	var abs_csproj := ProjectSettings.globalize_path(csproj)
	var configuration := str(params.get("configuration", "Debug"))
	var output: Array = []
	var args := PackedStringArray(["build", abs_csproj, "-c", configuration, "-v", "q"])
	var code := OS.execute("dotnet", args, output, true, false)
	var joined := "\n".join(output)
	return _router._ok({
		"ok": code == 0,
		"exit_code": code,
		"csproj": csproj,
		"configuration": configuration,
		"output": joined,
		"hint": (
			"Build succeeded — C# types are loadable after editor/game reload."
			if code == 0
			else "Build failed — see output; fix .cs then call godot_scripts_build_csharp again."
		),
	})


func _cmd_patch_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	# Phase 2 (#207): .cs patch is allowed when the build primitive exists; still
	# require a follow-up ``cmd_build_csharp`` before the change is loadable.
	if path.ends_with(".cs"):
		if not _router._csharp_build_ready():
			return _router._fail(
				"VALIDATION_ERROR",
				"patch_script for .cs needs csharp_build (dotnet CLI + .NET editor + .csproj). "
					+ "Use write_script for full-file authoring, or install the .NET SDK.",
				"script_path",
			)
		# Fall through to the shared patch path below (.cs treated like .gd bytes).
	elif not path.ends_with(".gd"):
		return _router._fail("VALIDATION_ERROR", "script_path must end with .gd or .cs.")
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	var find := str(params.get("find", ""))
	if find.is_empty():
		return _router._fail("VALIDATION_ERROR", "'find' must be a non-empty string.")
	var before_state := MCPReceipt.file_state(path)
	var content := FileAccess.get_file_as_string(path)
	var occurrences := content.count(find)
	if occurrences == 0:
		return _router._fail("VALIDATION_ERROR", "'find' text was not found in the script.")
	var patched := content.replace(find, str(params.get("replace", "")))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Patch script %s" % path, UndoRedo.MERGE_DISABLE, _router.asset_action_context())
	ur.add_do_method(_router, "_write_file_text", path, patched)
	ur.add_undo_method(_router, "_write_file_text", path, content)
	ur.commit_action()
	if FileAccess.get_file_as_string(path) != patched:
		return _router._ok({
			"script_path": path,
			"replacements": 0,
			"hint": "The editor did not keep the patched script content.",
			"receipt": MCPReceipt.make("noop", []),
		})
	var result := {
		"script_path": path,
		"replacements": occurrences,
		"receipt": MCPReceipt.make("updated", [
			MCPReceipt.change(path, "write", before_state, MCPReceipt.file_state(path)),
		]),
	}
	if path.ends_with(".cs"):
		result["hint"] = (
			"C# patch landed on disk but is not loadable until godot_scripts_build_csharp "
			+ "(or `dotnet build`) succeeds."
		)
	return _router._ok(result)


func _collect_scripts(directory: String, out: Array, language: String) -> void:
	var dir := DirAccess.open(directory)
	if dir == null:
		return
	var extension := ".gd" if language == "gd" else ".cs"
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := directory.path_join(name)
		if dir.current_is_dir():
			if not name.begins_with("."):
				_collect_scripts(full, out, language)
		elif name.ends_with(extension):
			out.append(full)
		name = dir.get_next()
	dir.list_dir_end()


