import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.workspace.dbus as DBus

PlasmoidItem {
    id: root
    property var snapshot: ({})
    property bool changing: false
    property bool loading: false
    property string feedback: "상태를 확인하는 중…"
    Plasmoid.icon: "preferences-system"
    toolTipMainText: "프리렌 OS 컨트롤러"
    toolTipSubText: snapshot.temperature !== undefined ? "CPU " + Math.round(snapshot.temperature) + "°C · 밝기 " + snapshot.brightness + "%" : feedback

    function request(member, args, callback) {
        DBus.SessionBus.asyncCall({service: "io.github.BumBoo.FrierenController",
            path: "/io/github/BumBoo/FrierenController",
            iface: "io.github.BumBoo.FrierenController1", member: member, arguments: args},
            function(reply) {
                callback(JSON.parse(reply.value));
            }, function(reply) {
                loading = false;
                changing = false;
                feedback = reply.error.message || "컨트롤러 연결을 확인해 주세요.";
            });
    }

    function refresh() {
        if (loading || changing) return;
        loading = true;
        request("Status", [], function(value) {
            snapshot = value;
            feedback = "";
            loading = false;
        });
    }

    function change(member, args) {
        if (changing) return;
        changing = true;
        request(member, args, function(value) {
            changing = false;
            refresh();
        });
    }

    Component.onCompleted: refresh()
    Timer { interval: 5000; repeat: true; running: !root.changing; onTriggered: root.refresh() }

    compactRepresentation: Controls.Label {
        text: root.snapshot.temperature !== undefined ? "❄ " + Math.round(root.snapshot.temperature) + "°" : "❄"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: Kirigami.Theme.textColor
        MouseArea { anchors.fill: parent; onClicked: root.expanded = !root.expanded }
    }

    fullRepresentation: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing
        Layout.minimumWidth: Kirigami.Units.gridUnit * 17
        Layout.minimumHeight: Kirigami.Units.gridUnit * 18
        Controls.Label { text: "프리렌 컨트롤러"; font.bold: true; font.pointSize: 14 }
        Controls.Label {
            text: root.snapshot.temperature !== undefined ? "CPU " + Math.round(root.snapshot.temperature) + "°C · " + root.snapshot.power_mode : "연결 확인 중"
            color: Kirigami.Theme.textColor
        }
        Controls.Label { text: "밝기 " + (root.snapshot.brightness || 0) + "%" }
        RowLayout {
            Controls.Button {
                text: "−"
                enabled: !root.changing && !root.snapshot.active_mode
                onClicked: root.change("SetBrightness", [DBus.INT32(Math.max(5, root.snapshot.brightness - 5))])
            }
            Controls.Slider {
                id: brightness
                Layout.fillWidth: true
                from: 5; to: 100; stepSize: 1
                value: root.snapshot.brightness || 50
                enabled: !root.changing && !root.snapshot.active_mode
                onMoved: if (!pressed) root.change("SetBrightness", [DBus.INT32(Math.round(value))])
                property bool dragging: false
                onPressedChanged: {
                    if (pressed) dragging = true;
                    else if (dragging) {
                        dragging = false;
                        root.change("SetBrightness", [DBus.INT32(Math.round(value))]);
                    }
                }
            }
            Controls.Button {
                text: "+"
                enabled: !root.changing && !root.snapshot.active_mode
                onClicked: root.change("SetBrightness", [DBus.INT32(Math.min(100, root.snapshot.brightness + 5))])
            }
        }
        Controls.Label { text: "작업 모드"; font.bold: true }
        Repeater {
            model: root.snapshot.modes || []
            Controls.Button {
                required property var modelData
                text: modelData.title + (root.snapshot.active_mode === modelData.id ? " · 사용 중" : "")
                Layout.fillWidth: true
                enabled: !root.changing
                onClicked: root.change("ApplyMode", [DBus.STRING(modelData.id)])
            }
        }
        Controls.Button {
            text: "모드 끝내기"
            Layout.fillWidth: true
            enabled: !!root.snapshot.active_mode && !root.changing
            onClicked: root.change("EndMode", [])
        }
        Controls.Label {
            text: root.feedback || (root.snapshot.active_mode ? "밝기를 직접 바꾸려면 모드를 먼저 끝내 주세요." : "")
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Item { Layout.fillHeight: true }
    }
}
