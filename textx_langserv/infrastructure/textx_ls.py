import logging
import hashlib
import os

from utils import _utils, uris
from utils.constants import TX_OUTLINE_COMMAND
from infrastructure import lsp
from infrastructure.language_server import LanguageServer
from infrastructure.workspace import Workspace
from infrastructure.configuration import Configuration

from capabilities.completions import completions
from capabilities.lint import lint
from capabilities.hover import hover
from capabilities.definitions import definitions
from capabilities.find_references import find_all_references

from commands.outline import OutlineTree

from infrastructure.dsl_handler import TxDslHandler

log = logging.getLogger(__name__)

class TextXLanguageServer(LanguageServer):

    workspace = None
    configuration = None
    dsl_extension = None
    tx_dsl_handlers = {}

    commands = {
        TX_OUTLINE_COMMAND: lambda ls, args: OutlineTree(
                                ls.tx_dsl_handlers[ls.dsl_extension].model_source,
                                ls.configuration.outline_model,
                                ls.tx_dsl_handlers[ls.dsl_extension].last_valid_model
                                            ).make_tree()
    }

    def capabilities(self):
        return {
            'codeActionProvider': True,
            'codeLensProvider': {
                'resolveProvider': False,
            },
            'completionProvider': {
                'resolveProvider': False,
                'triggerCharacters': ['.']
            },
            'documentFormattingProvider': True,
            # 'documentHighlightProvider': True,
            'documentRangeFormattingProvider': True,
            'documentSymbolProvider': True,
            'definitionProvider': True,
            'executeCommandProvider': {
                'commands': ['genext','outline.refresh']
            },
            'hoverProvider': True,
            'referencesProvider': True,
            'signatureHelpProvider': {
                'triggerCharacters': ['(', ',']
            },
            'textDocumentSync': lsp.TextDocumentSyncKind.INCREMENTAL
        }


    def initialize(self, root_uri, init_opts, _process_id):
        self.process_id = _process_id
        self.root_uri = root_uri
        self.init_opts = init_opts

        self.workspace = Workspace(root_uri, self)
        self.configuration = Configuration(root_uri)


    def m_text_document__did_close(self, textDocument=None, **_kwargs):
        # Remove document from workspace
        self.workspace.rm_document(textDocument['uri'])
        # Remove handler from dict
        del self.tx_dsl_handlers[self.dsl_extension]

    def m_text_document__did_open(self, textDocument=None, **_kwargs):
        # Add document to workspace
        self.workspace.put_document(textDocument['uri'], textDocument['text'], version=textDocument.get('version'))
        # Add model handler in dict
        self.tx_dsl_handlers[self.dsl_extension] = handler = TxDslHandler(self.configuration, self.dsl_extension)
        # Parse model and lint file
        self.tx_dsl_handlers[self.dsl_extension].parse_model(self.workspace.documents[textDocument['uri']].source)
        lint(textDocument['uri'], self.workspace, handler)

    def m_text_document__did_change(self, contentChanges=None, textDocument=None, **_kwargs):
        for change in contentChanges:
            self.workspace.update_document(
                textDocument['uri'],
                change,
                version=textDocument.get('version')
            )
        handler = self.tx_dsl_handlers[self.dsl_extension]
        handler.parse_model(self.workspace.documents[textDocument['uri']].source)
        lint(textDocument['uri'], self.workspace, handler)

    def m_text_document__did_save(self, textDocument=None, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        handler.parse_model(self.workspace.documents[textDocument['uri']].source)
        lint(textDocument['uri'], self.workspace, handler)

    def m_text_document__code_action(self, textDocument=None, range=None, context=None, **_kwargs):
        pass

    def m_text_document__code_lens(self, textDocument=None, **_kwargs):
        # return [{
        #     'range': {
        #         'start': {'line': 3, 'character': 2},
        #         'end': {'line': 3, 'character': 10}
        #     }
        # }]
        pass

    def m_text_document__completion(self, textDocument=None, position=None, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        handler.parse_model(self.workspace.documents[textDocument['uri']].source)
        model_source = self.workspace.get_document(textDocument['uri']).source
        return completions(model_source, position, handler)

    def m_text_document__definition(self, textDocument=None, position=None, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        handler.parse_model(self.workspace.documents[textDocument['uri']].source)
        return definitions(textDocument['uri'], position, handler)

    def m_text_document__hover(self, textDocument=None, position=None, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        return hover(textDocument['uri'], position, handler)

    def m_text_document__document_symbol(self, textDocument=None, **_kwargs):
        pass
    
    # def m_text_document__document_highlight(self, textDocument=None, **_kwargs):
    #     # return self.document_symbols(textDocument['uri'])
    #     pass

    def m_text_document__formatting(self, textDocument=None, options=None, **_kwargs):
        pass

    def m_text_document__range_formatting(self, textDocument=None, range=None, options=None, **_kwargs):
        pass

    def m_text_document__references(self, textDocument=None, position=None, context=None, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        handler.parse_model(self.workspace.documents[textDocument['uri']].source)
        return find_all_references(textDocument['uri'], position, context, handler)
        

    def m_text_document__signature_help(self, textDocument=None, position=None, **_kwargs):
        pass

    def m_workspace__did_change_configuration(self, settings=None):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        for doc_uri in self.workspace.documents:
            lint(doc_uri, self.workspace, handler)

    def m_workspace__did_change_watched_files(self, **_kwargs):
        handler = self.tx_dsl_handlers[self.dsl_extension]
        for change in _kwargs['changes']:
            # Check if configuration file is changed
            if uris.to_fs_path(change['uri']) == self.configuration.txconfig_uri:
                loaded = self.configuration.load_configuration()
                if loaded:
                    self.workspace.show_message("You have to reopen your tabs or restart vs code.")
                else:
                    self.workspace.show_message("Error in .txconfig file.")
            # TODO: Check if metamodel is changed
                


        # Externally changed files may result in changed diagnostics
        for doc_uri in self.workspace.documents:
            lint(doc_uri, self.workspace, handler)
        

    def m_workspace__execute_command(self, command=None, arguments=None):
        return self.commands[command](self, arguments)
