--[[--
MiningCat plugin: the dictionary popup shows the definitions of MiningCat's dictionaries (on the computer) with the
word's status there, and a "Send to MiningCat" button sends the word looked up, the text around it and the book to
MiningCat (Settings › E-reader there). MiningCat cuts the sentence from the text and keeps the word in its E-reader
inbox, where its card is made.

Words that can't be sent (Wi-Fi off, MiningCat closed) wait on the e-reader, and are sent once the Wi-Fi is back
or from the menu: Search › Settings › MiningCat.

@module koplugin.MiningCat
--]]--

local DataStorage = require("datastorage")
local InfoMessage = require("ui/widget/infomessage")
local InputDialog = require("ui/widget/inputdialog")
local LuaSettings = require("luasettings")
local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local logger = require("logger")
local T = require("ffi/util").template
local _ = require("gettext")

-- How many words of the book before and after the word are sent: MiningCat cuts its sentence from them.
local CONTEXT_WORDS = 80
-- Seconds to wait for MiningCat: on the local network, it answers at once or not at all. A lookup waits less: the
-- popup waits for it.
local TIMEOUT = 5
local LOOKUP_TIMEOUT = 3
-- The text after the word sent with a lookup, for the words longer than the selection (CJK: a word is a character).
local LOOKUP_CONTEXT_WORDS = 10

local STATUSES = { new = _("New"), learning = _("Learning"), known = _("Known"), ignored = _("Ignored") }
-- On top of KOReader's dictionary CSS, for the line of the word's status.
local CSS = [[
    .mc-status { margin: 0 0 0.5em 0; }
]]

local MiningCat = WidgetContainer:extend{
    name = "miningcat",
    is_doc_only = false,
}

function MiningCat:init()
    -- {url, token}: what Settings › E-reader shows in MiningCat
    self.settings = G_reader_settings:readSetting("miningcat", {})
    -- The words not sent yet, kept across restarts.
    self.queue_file = LuaSettings:open(DataStorage:getSettingsDir() .. "/miningcat_queue.lua")
    self.queue = self.queue_file:readSetting("words", {})
    math.randomseed(os.time())
    self.ui.menu:registerToMainMenu(self)
    self:registerDictButton()
    self:hookDictionary()
end

-- ------------------------------------------------------------------ the word looked up

function MiningCat:registerDictButton()
    if not (self.ui.document and self.ui.dictionary and self.ui.dictionary.addToDictButtons) then
        return
    end
    self.ui.dictionary:addToDictButtons{
        id = "miningcat_send",
        menu_text = _("Send to MiningCat"),
        text = _("Send to MiningCat"),
        insert_first = true,
        callback = function(dict_popup)
            self:send(self:wordOf(dict_popup))
        end,
    }
end

local function trim(text)
    return (text or ""):match("^%s*(.-)%s*$")
end

-- ------------------------------------------------------------------ MiningCat's dictionaries in the popup

function MiningCat:looksUp()
    return self.settings.lookup ~= false and trim(self.settings.url) ~= ""
end

-- The text after the word in the book, when the word looked up is the one selected.
function MiningCat:textAfter(word)
    local highlight = self.ui.highlight
    local selected = highlight and highlight.selected_text
    if not (selected and trim(selected.text) == word) then return "" end
    local ok, _prev, next = pcall(highlight.getSelectedWordContext, highlight, LOOKUP_CONTEXT_WORDS)
    return ok and next or ""
end

-- The line on top of a definition: the reading, the word's status in MiningCat, its frequency rank, and whether it
-- waits in the inbox already.
local function statusHtml(entry)
    local util = require("util")
    local function escape(text) return (util.htmlEscape(text)) end  -- one value: htmlEscape returns gsub's count too
    local status = type(entry.status) == "table" and entry.status or {}
    local parts = {}
    if type(entry.reading) == "string" and entry.reading ~= "" and entry.reading ~= entry.expression then
        table.insert(parts, escape(entry.reading))
    end
    local text = "<b>" .. (STATUSES[status.status] or STATUSES.new) .. "</b>"
    if type(status.linked) == "table" and status.status ~= status.linked.status then
        text = text .. T(_(" (%1 as %2)"), STATUSES[status.linked.status] or "", escape(status.linked.expression or ""))
    end
    table.insert(parts, text)
    if type(entry.frequency_rank) == "number" then
        table.insert(parts, T(_("frequency #%1"), entry.frequency_rank))
    end
    local html = '<p class="mc-status">' .. table.concat(parts, " · ")
    if entry.in_inbox then
        html = html .. "<br>" .. _("Sent already: waiting in MiningCat's inbox.")
    end
    return html .. "</p>"
end

-- KOReader's results for MiningCat's entries ({dict, word, definition}, one per definition), or nil and why.
function MiningCat:lookupResults(word)
    if not NetworkMgr:isConnected() then
        return nil, _("The Wi-Fi is off: MiningCat's dictionaries can't be reached.")
    end
    local result, err = self:request("POST", "/api/inbox/lookup", {
        word = word,
        after = self:textAfter(word),
        language = (self.ui.doc_props or {}).language,
    }, LOOKUP_TIMEOUT)
    if not result then return nil, err end
    local results = {}
    for _i, entry in ipairs(result.entries or {}) do
        local status = statusHtml(entry)
        for _i, definition in ipairs(entry.definitions or {}) do
            local html = status .. (definition.html or "")
            table.insert(results, {
                dict = definition.dictionary,
                word = entry.expression,
                definition = html,
                -- tidyMarkup() turns the definitions of dictionaries KOReader doesn't have into plain text:
                -- showDict() gives them their HTML back.
                miningcat_html = html,
            })
        end
    end
    return results
end

-- MiningCat's results come first, then those of KOReader's own dictionaries, if any. Without any of KOReader's
-- dictionaries, MiningCat's are looked up alone.
function MiningCat:hookDictionary()
    local dictionary = self.ui.dictionary
    if not dictionary or dictionary.miningcat_hooked then return end
    dictionary.miningcat_hooked = true
    local plugin = self
    local stardictLookup, startSdcv, showDict = dictionary.stardictLookup, dictionary.startSdcv, dictionary.showDict

    function dictionary:stardictLookup(word, dict_names, ...)
        plugin.alone = plugin:looksUp() and dict_names ~= nil and #dict_names == 0
        -- KOReader stops here when none of its dictionaries is enabled: nil lets the lookup go on.
        return stardictLookup(self, word, not plugin.alone and dict_names or nil, ...)
    end

    function dictionary:startSdcv(word, dict_names, fuzzy_search)
        local alone = plugin.alone
        plugin.alone = false
        if not plugin:looksUp() then
            return startSdcv(self, word, dict_names, fuzzy_search)
        end
        local results, err = plugin:lookupResults(word)
        if alone then
            if results and #results > 0 then return results end
            return {{
                dict = _("MiningCat"),
                word = word,
                definition = err or _("No results."),
                no_result = err == nil,
            }}
        end
        local own = startSdcv(self, word, dict_names, fuzzy_search)
        if not results or #results == 0 then return own end
        for _i, r in ipairs(own) do
            if not r.no_result and r.dict ~= "" then table.insert(results, r) end
        end
        return results
    end

    function dictionary:showDict(word, results, ...)
        for _i, r in ipairs(results or {}) do
            if r.miningcat_html then
                r.definition, r.is_html, r.css = r.miningcat_html, true, CSS
            end
        end
        return showDict(self, word, results, ...)
    end
end

-- Where the word is in the book: "p. 12 / 140".
function MiningCat:location(selected)
    local document = self.ui.document
    local ok, page = pcall(function()
        if selected and type(selected.pos0) == "string" then
            return document:getPageFromXPointer(selected.pos0)  -- reflowable books (EPUB...)
        elseif selected and type(selected.pos0) == "table" and selected.pos0.page then
            return selected.pos0.page  -- fixed layout (PDF...)
        end
        return self.ui:getCurrentPage()
    end)
    if not ok or not page then return "" end
    local ok_total, total = pcall(document.getPageCount, document)
    return ok_total and total and T("p. %1 / %2", page, total) or T("p. %1", page)
end

-- What is sent to MiningCat: the word selected in the book and the text around it. A word typed in the dictionary
-- (no selection) goes without its sentence.
function MiningCat:wordOf(dict_popup)
    local highlight = self.ui.highlight
    local selected = highlight and highlight.selected_text
    local word = trim(selected and selected.text or dict_popup.word)
    local before, after = "", ""
    if selected and selected.text then
        local ok, prev, next = pcall(highlight.getSelectedWordContext, highlight, CONTEXT_WORDS)
        if ok then
            before, after = prev or "", next or ""
        end
    end
    local props = self.ui.doc_props or {}
    return {
        uid = T("%1-%2", os.time(), math.random(1, 1e9)),
        word = word,
        before = before,
        after = after,
        language = props.language,
        book = props.display_title or props.title or "",
        location = self:location(selected),
        sent = os.time(),
    }
end

-- ------------------------------------------------------------------ talking to MiningCat

-- Returns the decoded answer, or nil, the error and the HTTP status (nil when MiningCat can't be reached).
function MiningCat:request(method, path, body, timeout)
    local http = require("socket.http")
    local json = require("rapidjson")
    local ltn12 = require("ltn12")
    local socket = require("socket")
    local socketutil = require("socketutil")

    local url = trim(self.settings.url)
    if url == "" then
        return nil, _("MiningCat's address isn't set: Search › Settings › MiningCat.")
    end
    if not url:match("^https?://") then url = "http://" .. url end
    local payload = body and json.encode(body)
    local headers = {
        ["Authorization"] = "Bearer " .. trim(self.settings.token),
        ["Accept"] = "application/json",
    }
    if payload then
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = tostring(#payload)
    end
    local sink = {}
    timeout = timeout or TIMEOUT
    socketutil:set_timeout(timeout, timeout * 2)
    local code = socket.skip(1, http.request{
        url = url:gsub("/+$", "") .. path,
        method = method,
        headers = headers,
        source = payload and ltn12.source.string(payload) or nil,
        sink = ltn12.sink.table(sink),
    })
    socketutil:reset_timeout()
    if type(code) ~= "number" then
        logger.warn("MiningCat: can't reach", url, code)
        return nil, T(_("MiningCat can't be reached at %1 (%2)."), url, tostring(code))
    end
    local ok, data = pcall(json.decode, table.concat(sink))
    if code ~= 200 then
        local message = ok and type(data) == "table" and type(data.error) == "string" and data.error
        return nil, message or T(_("MiningCat answered with an error (%1)."), code), code
    end
    return ok and type(data) == "table" and data or {}
end

function MiningCat:saveQueue()
    self.queue_file:saveSetting("words", self.queue)
    self.queue_file:flush()
end

-- Sends the words waiting, oldest first. Stops at the first one MiningCat doesn't get (it keeps waiting), but drops
-- those MiningCat refuses (400: they would never go). Returns how many were sent, and the error that stopped it.
function MiningCat:flush()
    local sent, refused = 0, {}
    while #self.queue > 0 do
        local word = self.queue[1]
        local result, err, code = self:request("POST", "/api/inbox", word)
        if not result and code ~= 400 then
            self:saveQueue()
            return sent, err, refused
        end
        table.remove(self.queue, 1)
        if result then
            sent = sent + 1
        else
            logger.warn("MiningCat refused", word.word, err)
            table.insert(refused, T("%1: %2", word.word, err))
        end
    end
    self:saveQueue()
    return sent, nil, refused
end

local function notify(text, timeout)
    UIManager:show(InfoMessage:new{ text = text, timeout = timeout })
end

local function refusedText(refused)
    return T(_("Refused by MiningCat:\n%1"), table.concat(refused, "\n"))
end

-- A message, then the words MiningCat refused, if any.
local function withRefused(text, refused)
    if #refused == 0 then return text end
    return text ~= "" and text .. "\n\n" .. refusedText(refused) or refusedText(refused)
end

function MiningCat:send(word)
    if word.word == "" then return end
    table.insert(self.queue, word)
    self:saveQueue()
    -- Without Wi-Fi, the word waits: turning the Wi-Fi on for each word would drain the battery.
    if not NetworkMgr:isConnected() then
        return notify(T(_("Kept on the e-reader: %1 word(s) waiting.\nThey'll be sent once the Wi-Fi is on."), #self.queue), 3)
    end
    local sent, err, refused = self:flush()
    if err then
        notify(withRefused(T(_("%1\n\nKept on the e-reader: %2 word(s) waiting."), err, #self.queue), refused), 5)
    elseif #refused > 0 then
        notify(refusedText(refused), 5)
    else
        notify(sent > 1 and T(_("Sent to MiningCat (%1 words)."), sent) or _("Sent to MiningCat."), 1)
    end
end

-- Back on the Wi-Fi: the words waiting go.
function MiningCat:onNetworkConnected()
    if #self.queue == 0 or trim(self.settings.url) == "" then return end
    UIManager:scheduleIn(2, function()
        if #self.queue == 0 then return end
        local sent, _err, refused = self:flush()
        if sent > 0 or #refused > 0 then
            notify(withRefused(T(_("Sent to MiningCat: %1 word(s)."), sent), refused), 3)
        end
    end)
end

-- ------------------------------------------------------------------ settings

function MiningCat:editSetting(key, title, hint, description, touchmenu_instance)
    local dialog
    dialog = InputDialog:new{
        title = title,
        input = self.settings[key] or "",
        input_hint = hint,
        description = description,
        buttons = {{
            {
                text = _("Cancel"),
                id = "close",
                callback = function() UIManager:close(dialog) end,
            },
            {
                text = _("Save"),
                is_enter_default = true,
                callback = function()
                    self.settings[key] = trim(dialog:getInputText())
                    G_reader_settings:saveSetting("miningcat", self.settings)
                    UIManager:close(dialog)
                    if touchmenu_instance then touchmenu_instance:updateItems() end
                end,
            },
        }},
    }
    UIManager:show(dialog)
    dialog:onShowKeyboard()
end

function MiningCat:testConnection()
    NetworkMgr:runWhenConnected(function()
        local result, err = self:request("GET", "/api/inbox/ping")
        if not result then return notify(err) end
        local language = type(result.language) == "table" and result.language.name
        notify(language and T(_("Connected to MiningCat.\nYou study %1."), language) or _("Connected to MiningCat."))
    end)
end

function MiningCat:addToMainMenu(menu_items)
    menu_items.miningcat = {
        text = _("MiningCat"),
        sorting_hint = "search_settings",
        sub_item_table = {
            {
                text_func = function()
                    local url = trim(self.settings.url)
                    return T(_("Address: %1"), url ~= "" and url or _("not set"))
                end,
                keep_menu_open = true,
                callback = function(touchmenu_instance)
                    self:editSetting("url", _("MiningCat's address"), "http://192.168.1.10:5051",
                        _("Shown in MiningCat: Settings › E-reader."), touchmenu_instance)
                end,
            },
            {
                text_func = function()
                    return trim(self.settings.token) ~= "" and _("Token: set") or _("Token: not set")
                end,
                keep_menu_open = true,
                callback = function(touchmenu_instance)
                    self:editSetting("token", _("MiningCat's token"), "abcde-fghij",
                        _("Shown in MiningCat: Settings › E-reader."), touchmenu_instance)
                end,
            },
            {
                text = _("Look words up in MiningCat's dictionaries"),
                checked_func = function() return self.settings.lookup ~= false end,
                callback = function()
                    self.settings.lookup = self.settings.lookup == false
                    G_reader_settings:saveSetting("miningcat", self.settings)
                end,
            },
            {
                text = _("Test the connection"),
                keep_menu_open = true,
                separator = true,
                callback = function() self:testConnection() end,
            },
            {
                text_func = function()
                    return T(_("Send the words waiting (%1)"), #self.queue)
                end,
                enabled_func = function() return #self.queue > 0 end,
                keep_menu_open = true,
                callback = function(touchmenu_instance)
                    NetworkMgr:runWhenConnected(function()
                        local sent, err, refused = self:flush()
                        local text = T(_("Sent: %1 word(s). Still waiting: %2."), sent, #self.queue)
                        notify(withRefused(err and err .. "\n\n" .. text or text, refused))
                        touchmenu_instance:updateItems()
                    end)
                end,
            },
        },
    }
end

return MiningCat
