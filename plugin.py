#!/usr/bin/env python
import traceback
import websocket
import json
import logging
import threading

logging.basicConfig(level=logging.INFO)

MAX_ERRORS = 5

class StreamDeck:
    """ Handles communications to and from the websocket server. """
    def __init__(self, port: int, info: str, uuid: str, event: str, plugin: SDPlugin):
        """
        :param port: WebSocket server port received from the API
        :param info: Info string received from the API
        :param uuid: The uuid of the plugin
        :param event: Event string received from the API
        :param plugin: The SDPlugin object that handles processing of the events
        """
        self.port = port
        self.uuid = uuid
        self.info = info
        self.event = event
        self.plugin = plugin
        self.socket = websocket.WebSocketApp(f"ws://127.0.0.1:{str(self.port)}", on_open=self.on_open,
                                             on_close=self.on_close, on_message=self.on_message)

        logging.debug(f"info: {info}")

        # Define functions to handle events after they've been processed
        # These are low-level handlers, called before any of the plugin's On* functions
        # They allow raw handling of the messages from the websocket
        self.on_open_handler = None
        self.on_message_handler = None
        self.on_close_handler = None
        self.running = False

        self.errors = {}

    def image_loop(self):
        """
        Loop for updating button images, for those that need it
        """
        while self.running:
            for ctx in self.plugin.contexts:
                try:
                    self.plugin.on_loop(ctx)
                except Exception as e:
                    if not ctx in self.errors:
                        self.errors[ctx] = 0

                    self.errors[ctx] += 1
                    logging.error(f"on_loop() error: {e}")
                    traceback.print_exc()

                    if self.errors[ctx] >= MAX_ERRORS:
                        self.plugin.ShowAlert(ctx)
                        self.running = False
                        break

            # Wait 0.2 seconds before continuing the loop
            event = threading.Event()
            event.wait(timeout=0.2)

    def run(self):
        """
        Starts the websocket client and image loop thread.
        """
        self.running = True
        logging.info(f"Starting websocket client on port {self.port}")
        threading.Thread(target=self.image_loop).start()
        self.socket.run_forever()

    def register(self):
        """
        Register the plugin with the WebSocket so it can be used
        """
        event = {"event": self.event, "uuid": self.uuid}
        self.socket.send(json.dumps(event))
        logging.debug(f"Sent register payload: event: {event} uuid: {self.uuid}")

    def on_open(self, _):
        """
        Handles when the WebSocket is opened and automatically registers the plugin
        """
        self.register()

        if self.on_open_handler:
            self.on_open_handler()

    def on_close(self, _, status_code: int, msg: str):
        """
        Handles when the WebSocket is closed
        :param _: The WebSocket itself, which we do not need
        :param status_code: Status code returned from the WebSocket
        :param msg: Message returned from the WebSocket
        :return: None
        """
        logging.info(f"Closed with status code {status_code} with message {msg}")
        self.running = False

        if self.on_close_handler:
            self.on_close_handler()

    def on_message(self, _, msg: str):
        """
        This is the main WebSocket handler, which is called any time a message is received
        :param _: The WebSocket itself, which we do not need
        :param msg: The received message (raw string), that is usually JSON
        :return: None
        """
        try:
            # If there's a message handler set, call it before anything else
            if self.on_message_handler:
                self.on_message_handler(msg)

            parsed = json.loads(msg)
            # Only handle the parsed data if it's a dictionary
            # Anything else can be handled by the on_message_handler (if set)
            if isinstance(parsed, dict):
                event = parsed.get("event")

                # Handle exceptions to the conversion like so:
                #  if event == "exceptionName":
                #      method_name = "functionNameHere"

                # Get the method name to call for the received event
                # Convert first letter to uppercase: 'keyDown' -> 'onKeyDown'
                method_name = f"on{event[0].upper()}{event[1:]}"

                handler = getattr(self.plugin, method_name, None)
                if handler:
                    # systemDidWakeUp does not take any parameters
                    if event == "systemDidWakeUp":
                        handler()
                    else:
                        handler(parsed)
                else:
                    logging.error(f"No handler implemented for: {method_name}")

        except Exception as e:
            logging.error(f"Exception raised while handling message: {e}")
            traceback.print_exc()

class SDPlugin:
    """ Handles the messages received from the websocket server.
    See https://docs.elgato.com/streamdeck/sdk/references/websocket/plugin for the API """

    def __init__(self, port: int, info: str, uuid: str, event: str):
        """
        :param port: WebSocket server port received from the API
        :param info: Info string received from the API
        :param uuid: The uuid of the plugin
        :param event: Event string received from the API
        """
        self.sd: StreamDeck = StreamDeck(port, info, uuid, event, self)
        self.contexts = []  # list of contexts (individual instances of the plugin)
        self.ctxSettings = {}  # dictionary of settings, where the key is the context
        self.ctxInfo = {} # dictionary of context information (position, etc)
        self.settings = {} # dictionary of global settings
        self.logger = logging.getLogger("SDPlugin")

    def run(self):
        self.sd.run()

    def on_loop(self, context: str):
        """
        Called any time the image_loop() function from the StreamDeck class loops. Plugins can override this for their loop to be called
        :param context: Context provided by the WebSocket for the button
        :return: None
        """
        pass

    def setSettings(self, payload: dict):
        """
        Sets the context's settings and information from the given payload
        :param payload: Payload called anytime WillAppear and GetSettings are called
        :return: None
        """
        context = payload["context"]
        if context not in self.contexts:
            self.contexts.append(context)
        self.ctxSettings[context] = payload["payload"]["settings"]
        self.ctxInfo[context] = {"coordinates": payload["payload"]["coordinates"], "controller": payload["payload"]["controller"],
                   "state": payload["payload"]["state"], "isInMultiAction": payload["payload"]["isInMultiAction"], "action": payload["action"]}

    def removeSettings(self, payload: dict):
        """
        Removes the context's settings and information based on the given payload
        :param payload: Payload called anytime WillDisappear is called
        :return: None
        """
        context = payload["context"]
        self.contexts.pop(self.contexts.index(context)) # Remove the context from the list of contexts
        # Remove the context settings and info
        del self.ctxSettings[context]
        del self.ctxInfo[context]


    # Request various parameters from the Stream Deck API
    # These are following the casing of Elgato's own API
    def GetSettings(self, context: str):
        payload = {"context": context, "event": "getSettings"}
        self.sd.socket.send(json.dumps(payload))

    def GetGlobalSettings(self, context: str):
        payload = {"context": context, "event": "getGlobalSettings"}
        self.sd.socket.send(json.dumps(payload))

    def GetResources(self, context: str):
        payload = {"context": context, "event": "getResources"}
        self.sd.socket.send(json.dumps(payload))

    def GetSecrets(self, context: str):
        payload = {"context": context, "event": "getSecrets"}
        self.sd.socket.send(json.dumps(payload))

    def LogMessage(self, msg: str):
        payload = {"event": "logMessage", "payload": {"message": msg}}
        self.sd.socket.send(json.dumps(payload))

    def OpenUrl(self, url: str):
        payload = {"event": "openUrl", "payload": {"url": url}}
        self.sd.socket.send(json.dumps(payload))

    # Send various parameters to the Stream Deck API
    def SendToPropertyInspector(self, context: str, data: dict):
        payload = {"event": "sendToPropertyInspector", "context": context, "payload": data}
        self.sd.socket.send(json.dumps(payload))

    def SetGlobalSettings(self, context: str, data: dict):
        payload = {"event": "setGlobalSettings", "context": context, "payload": data}
        self.sd.socket.send(json.dumps(payload))

    def SetSettings(self, context: str, data: dict):
        payload = {"event": "setSettings", "context": context, "payload": data}
        self.logger.debug(f"Settings Payload: {payload}")
        self.sd.socket.send(json.dumps(payload))

    def SetFeedback(self, context: str, data: dict):
        raise NotImplementedError

    def SetFeedbackLayout(self, context: str, layout: str):
        payload = {"event": "setFeedbackLayout", "context": context, "payload": {"layout": layout}}
        self.sd.socket.send(json.dumps(payload))

    def SetImage(self, context: str, image: str | None = None, state: int | None = None, target: str | None = None):
        payload = {"context": context, "event": "setImage", "payload":
            {"image": image, "state": state, "target": target}}
        self.sd.socket.send(json.dumps(payload))

    def SetResources(self, context: str, data: dict):
        payload = {"event": "setResources", "context": context, "payload": data}
        self.sd.socket.send(json.dumps(payload))

    def SetState(self, context: str, state: int):
        if state < 0 or state > 1:
            raise ValueError("State must be between 0 and 1")
        payload = {"event": "setState", "context": context, "payload": {"state": state}}
        self.sd.socket.send(json.dumps(payload))

    def SetTitle(self, context: str, title: str | None, state: int | None, target: str | None):
        payload = {"event": "setTitle", "context": context, "payload": {"title": title, "state": state, "target": target}}
        self.sd.socket.send(json.dumps(payload))

    def SetTriggerDescription(self, context: str, longTouch: str | None = None, push: str | None = None,
                              rotate: str | None = None, touch: str | None = None):
        payload = {"event": "setTriggerDescription", "context": context, "payload": {
            "longTouch": longTouch, "push": push, "rotate": rotate, "touch": touch
        }}
        self.sd.socket.send(json.dumps(payload))

    def ShowAlert(self, context: str):
        payload = {"event": "showAlert", "context": context}
        self.sd.socket.send(json.dumps(payload))

    def ShowOk(self, context: str):
        payload = {"event": "showOk", "context": context}
        self.sd.socket.send(json.dumps(payload))

    def SwitchToProfile(self, context: str, device: str, page: int | None = None, profile: str | None = None):
        payload = {"context": context, "device": device, "event": "switchToProfile", "payload": {
            "page": page, "profile": profile
        }}
        self.sd.socket.send(json.dumps(payload))

    # Settings retrieval API Handlers
    # The plugin may override this, but it should still call it
    def onDidReceiveSettings(self, payload: dict):
        self.setSettings(payload)

    def onDidReceiveGlobalSettings(self, payload: dict):
        self.logger.debug(f"Global Settings Payload: {payload}")

    # Handles when the plugin is loaded on the current page or removed
    # Plugins may also override this, but should still call it
    def onWillAppear(self, payload: dict):
        self.setSettings(payload)

    def onWillDisappear(self, payload: dict):
        self.removeSettings(payload)

    # WebSocket API Handlers to be defined in the actual plugin
    def onSendToPlugin(self, payload: dict):
        pass

    def onApplicationDidLaunch(self, payload: dict):
        pass

    def onApplicationDidTerminate(self, payload: dict):
        pass

    def onDeviceDidChange(self, payload: dict):
        pass

    def onDeviceDidConnect(self, payload: dict):
        pass

    def onDeviceDidDisconnect(self, payload: dict):
        pass

    def onDialDown(self, payload: dict):
        pass

    def onDialRotate(self, payload: dict):
        pass

    def onDialUp(self, payload: dict):
        pass

    def onDidReceiveDeepLink(self, payload: dict):
        pass

    def onDidReceivePropertyInspectorMessage(self, payload: dict):
        pass

    def onDidReceiveResources(self, payload: dict):
        pass

    def onDidReceiveSecrets(self, payload: dict):
        pass

    def onKeyDown(self, payload: dict):
        pass

    def onKeyUp(self, payload: dict):
        pass

    def onPropertyInspectorDidAppear(self, payload: dict):
        pass

    def onPropertyInspectorDidDisappear(self, payload: dict):
        pass

    def onSystemDidWakeUp(self):
        pass

    def onTitleParametersDidChange(self, payload: dict):
        pass

    def onTouchTap(self, payload: dict):
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plugin parameters")
    parser.add_argument("-port", type=int)
    parser.add_argument("-info", type=str)
    parser.add_argument("-pluginUUID", type=str)
    parser.add_argument("-registerEvent", type=str)

    args = parser.parse_args()

    plugin = SDPlugin(args.port, args.info, args.pluginUUID, args.registerEvent)
    plugin.run()