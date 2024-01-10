import json
import os
import argparse
from google.cloud import discoveryengine_v1alpha
from google.cloud import dialogflowcx_v3

#
# python chat-engine.py --project="gsd-tests-geai-marketing" --app-name=my_app --company-name=my_company --uris="support.google.com/google-ads/*"
#

parser = argparse.ArgumentParser()
parser.add_argument("--project", help="Id of project to use", type=str)
parser.add_argument("--location", help="Location to deploy",
                    type=str, default="global")
parser.add_argument("--app-name", help="Application name", type=str)
parser.add_argument("--company-name", help="Name of your company", type=str)
parser.add_argument(
    "--uris", help="Datastore uris to index comma separated", type=str)
parser.add_argument(
    "--datastore-storage-folder", help="Datastore uris to index comma separated", type=str, default="cloud-samples-data/dialogflow-cx/arc-lifebloo")
parser.add_argument(
    "--agent-name", help="Dialogflow CX agent name", type=str, default="Donate")
parser.add_argument(
    "--agent-identity", help="Dialogflow CX agent name", type=str, default="chatbot")
parser.add_argument(
    "--agent-description", help="Dialogflow CX agent name", type=str, default="Save a life, a fictitious organization")
parser.add_argument(
    "--agent-scope", help="Dialogflow CX agent name", type=str, default="humans with eligibility information")

dict_args = parser.parse_args()

print(f"Using arguments: {dict_args}")

project_id = dict_args.project
default_location = dict_args.location
app_name = dict_args.app_name
company_name = dict_args.company_name
uris = dict_args.uris.split(",")
datastore_storage_folder = dict_args.datastore_storage_folder
agent_config = {
    'name': dict_args.agent_name,
    'identity': dict_args.agent_identity,
    'description': dict_args.agent_description,
    'scope': dict_args.agent_scope
}


def create_chat_app():

    # Create a client
    datastore_client = discoveryengine_v1alpha.DataStoreServiceClient()

    # Initialize Datastore request argument(s) for Search
    parent_collection = f"projects/{project_id}/locations/{default_location}/collections/default_collection"
    datastore_name = f"{app_name}_datastore"
    datastore_id = f"{datastore_name}"

    # check if datastore exists
    try:
        datastore = datastore_client.get_data_store(request=discoveryengine_v1alpha.GetDataStoreRequest(
            name=f"{parent_collection}/dataStores/{datastore_id}",
        ))
        print(f"Datastore already exist: {datastore}")
    except:
        # Create datastore
        datastore = discoveryengine_v1alpha.DataStore(
            display_name=datastore_name,
            industry_vertical="GENERIC",
            solution_types=["SOLUTION_TYPE_CHAT"],
            content_config="PUBLIC_WEBSITE",
        )

        datastore_request = discoveryengine_v1alpha.CreateDataStoreRequest(
            parent=parent_collection,
            data_store=datastore,
            create_advanced_site_search=True,
            data_store_id=datastore_id
        )
        print(f"Creating datastore: {datastore_request}")
        datastore_client.create_data_store(request=datastore_request)

        site_search_engine_service_client = discoveryengine_v1alpha.SiteSearchEngineServiceClient()
        for uri in uris:
            target_site = discoveryengine_v1alpha.TargetSite()
            target_site.provided_uri_pattern = uri
            print(f"Creating Target site: {target_site}")
            site_search_engine_service_client.create_target_site(request=discoveryengine_v1alpha.CreateTargetSiteRequest(
                parent=f"{parent_collection}/dataStores/{datastore_id}/siteSearchEngine",
                target_site=target_site,
            ))

    # Creating dialogflow cx agent
    dcx_client = dialogflowcx_v3.AgentsClient()
    # check if datastore exists

    list_response = dcx_client.list_agents(request=dialogflowcx_v3.ListAgentsRequest(
        parent=f"projects/{project_id}/locations/{default_location}",
    ))

    agent = None
    for a in list_response.agents:
        if a.display_name == company_name:
            agent = a
            print(f"Agent already exist: {agent}")
            break
    # Consider pagination in this request

    if agent == None:
        agent = dialogflowcx_v3.Agent()
        agent.display_name = f"{company_name}"
        agent.default_language_code = "en"
        agent.time_zone = "America/Los_Angeles"

        dcx_agent_request = dialogflowcx_v3.CreateAgentRequest(
            parent=f"projects/{project_id}/locations/{default_location}",
            agent=agent,
        )
        print(f"Creating Agent: {dcx_agent_request}")
        agent = dcx_client.create_agent(request=dcx_agent_request)

    # Creating search engine client
    engine_client = discoveryengine_v1alpha.EngineServiceClient()

    # Initialize chat engine request arguments
    chat_engine_name = f"{app_name}_chat_engine"
    engine_id = f"{chat_engine_name}"
    try:
        engine = engine_client.get_engine(request=discoveryengine_v1alpha.GetEngineRequest(
            name=f"{parent_collection}/engines/{engine_id}"
        ))
        print(f"Engine already exist: {engine}")
    except:
        # Engine config and LLM features
        engine_config = discoveryengine_v1alpha.types.Engine.ChatEngineConfig()
        engine_config.dialogflow_agent_to_link = agent.name
        # Engine
        engine = discoveryengine_v1alpha.Engine(
            chat_engine_config=engine_config,
            display_name=chat_engine_name,
            solution_type="SOLUTION_TYPE_CHAT",
            data_store_ids=[datastore_id],
            common_config={'company_name': company_name},
        )

        engine_request = discoveryengine_v1alpha.CreateEngineRequest(
            parent=parent_collection,
            engine=engine,
            engine_id=engine_id
        )
        print(f"Creating engine: {engine_request}")
        engine_client.create_engine(request=engine_request)

    # Enabling GenAI features for Dialogflow CX Agent
    connector_settings = dialogflowcx_v3.types.GenerativeSettings.KnowledgeConnectorSettings(
        business=company_name,
        agent=agent_config["name"],
        agent_identity=agent_config["identity"],
        business_description=agent_config["description"],
        agent_scope=agent_config["scope"]
    )
    genai_settings = dialogflowcx_v3.types.GenerativeSettings(
        name=f"{agent.name}/generativeSettings",
        knowledge_connector_settings=connector_settings,
        language_code="en"
    )
    genai_settings_request = dialogflowcx_v3.UpdateGenerativeSettingsRequest(
        generative_settings=genai_settings
    )

    dcx_client.update_generative_settings(
        request=genai_settings_request
    )

    # Configuring default flow with GenAI features
    flow_client = dialogflowcx_v3.FlowsClient()

    default_flow = flow_client.get_flow(request=dialogflowcx_v3.GetFlowRequest(
        name=agent.start_flow
    ))

    # Verify domain to attach this datastore
    data_store_connection = dialogflowcx_v3.types.DataStoreConnection(
        data_store_type='PUBLIC_WEB',
        data_store=f"{parent_collection}/dataStores/{datastore_id}"
    )

    knowledge_connector_settings = dialogflowcx_v3.types.KnowledgeConnectorSettings(
        enabled=True,
        data_store_connections=[data_store_connection]
    )

    default_flow.knowledge_connector_settings = knowledge_connector_settings

    sys_no_match_default = dialogflowcx_v3.types.EventHandler(
        name='sys.no-match-default',
        event='sys.no-match-default',
        trigger_fulfillment=dialogflowcx_v3.types.Fulfillment(
            enable_generative_fallback=True
        )
    )
    sys_no_input_default = dialogflowcx_v3.types.EventHandler(
        name='sys.no-input-default',
        event='sys.no-input-default',
        trigger_fulfillment=dialogflowcx_v3.types.Fulfillment(
            enable_generative_fallback=True
        )
    )

    default_flow.event_handlers = [
        sys_no_match_default,
        sys_no_input_default
    ]

    request = dialogflowcx_v3.UpdateFlowRequest(
        flow=default_flow,
    )
    flow_client.update_flow(request=request)

    # Training the flow after this changes
    flow_client.train_flow(request=dialogflowcx_v3.TrainFlowRequest(
        name=agent.start_flow,
    ))

    os.putenv("SEARCH_DATASTORE",f"{parent_collection}/dataStores/{datastore_id}")
    os.putenv("SEARCH_DATASTORE_ID", datastore_id)
    os.putenv("SEARCH_ENGINE",f"{parent_collection}/engines/{engine_id}")
    os.putenv("AGENT_ENGINE",agent.name)

    with open("marketingEnvValue.json", "r") as jsonFile:
        data = json.load(jsonFile)
        data["AGENT_ENGINE_NAME"] = agent.name
        data["AGENT_LANGUAGE_CODE"] = agent.default_language_code
    with open("marketingEnvValue.json", "w") as jsonFile:
        json.dump(data, jsonFile)

    print(f"""Chat engine app results:
          Datastore: {parent_collection}/dataStores/{datastore_id}
          App: {parent_collection}/engines/{engine_id}
          Dialogflow CX Agent: {agent.name}
          """)


if __name__ == "__main__":
    create_chat_app()