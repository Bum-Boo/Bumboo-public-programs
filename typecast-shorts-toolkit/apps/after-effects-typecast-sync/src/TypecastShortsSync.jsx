#include "aeLayerUtils.jsx"
#include "aeImportUtils.jsx"
#include "aeCaptionGenerator.jsx"

(function TypecastShortsSync(thisObj) {
  function buildPanel(thisObj) {
    var panel = thisObj instanceof Panel
      ? thisObj
      : new Window("palette", "Typecast Shorts Sync", undefined, { resizeable: true });

    panel.orientation = "column";
    panel.alignChildren = ["fill", "top"];
    panel.spacing = 8;
    panel.margins = 12;

    var title = panel.add("statictext", undefined, "Typecast Shorts Sync");
    title.graphics.font = ScriptUI.newFont(title.graphics.font.name, "BOLD", 14);

    var folderGroup = panel.add("group");
    folderGroup.orientation = "row";
    folderGroup.alignChildren = ["fill", "center"];

    var selectButton = folderGroup.add("button", undefined, "Select Typecast Folder");
    var generateButton = panel.add("button", undefined, "Generate Captions");
    var adjustDuration = panel.add("checkbox", undefined, "Adjust comp duration to audio");
    adjustDuration.value = true;

    var status = panel.add("edittext", undefined, "No folder selected.", {
      multiline: true,
      readonly: true,
      scrolling: true
    });
    status.preferredSize = [360, 180];

    var state = {
      folder: null,
      job: null
    };

    function setStatus(text) {
      status.text = text;
    }

    function selectedComp() {
      if (!app.project) {
        return null;
      }

      var item = app.project.activeItem;
      return item instanceof CompItem ? item : null;
    }

    selectButton.onClick = function () {
      var folder = Folder.selectDialog("Select a Typecast job folder");

      if (!folder) {
        return;
      }

      state.folder = folder;
      state.job = TCSS_AE.discoverJobFolder(folder);
      setStatus(TCSS_AE.formatJobStatus(state.job, selectedComp()));
    };

    generateButton.onClick = function () {
      var comp = selectedComp();

      if (!comp) {
        setStatus("Select or open a composition before generating captions.");
        return;
      }

      if (!state.job) {
        setStatus("Select a Typecast folder first.");
        return;
      }

      app.beginUndoGroup("Typecast Shorts Sync");
      try {
        var result = TCSS_AE.generateCaptions(comp, state.job, {
          adjustDuration: adjustDuration.value
        });
        setStatus(TCSS_AE.formatGenerationStatus(result, comp));
      } catch (error) {
        setStatus("Generation failed:\n" + error.toString());
      } finally {
        app.endUndoGroup();
      }
    };

    panel.onResizing = panel.onResize = function () {
      this.layout.resize();
    };

    return panel;
  }

  var panel = buildPanel(thisObj);

  if (panel instanceof Window) {
    panel.center();
    panel.show();
  }
})(this);
