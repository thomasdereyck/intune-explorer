#!/usr/bin/env python3
# Copyright 2021, Thomas De Reyck.
# Copyright holders are not liable for any negative effects experienced from the use of this script.
# Version 0.1.1 - 2022-03-17

# Requirements:
# - Python 3, from python.org.
# - requests module. Install as root/administrator with the following command: "pip install requests".
# - An app registration in Azure AD with the following permissions set up:
#   - DeviceManagementApps.Read.All
#   - DeviceManagementConfiguration.Read.All
#   - DeviceManagementManagedDevices.Read.All
#   - DeviceManagementServiceConfig.Read.All
#   - Group.Read.All

# Configuration. Set these to correct values for your tenant:
## To make things load faster, only groups with this prefix will be examined. You can put an empty string, but that will impact performance.
## It is required to use --reload after switching prefixes to first load the correct data.
group_prefix = ""
## The tenant ID of your Azure AD instance.
tenant_id = ""
## The ID of the app registration as defined in your Azure AD.
client_id = ""
## The corresponding secret for the app registration.
client_secret = ""
## Enabling the beta Graph API shows additional data (e.g. scripts, deployment profiles, ...)
beta_enabled = True
## Cache database location. If set to None, then it's stored in a temp folder by default, which is fine.
## If you want a fixed location, use e.g "/home/thomas/cache.db" or "C:\Users\Thomas\cache.db".
cache_database_path = None

import requests
import json
import sqlite3
import argparse
import tempfile
import getpass
import os

if not cache_database_path:
    cache_database_path = os.path.join(tempfile.gettempdir(), "intune-explorer-cache-" + getpass.getuser() + "-" + group_prefix + ".db")

class TokenException(Exception):
    pass

class GraphAPI:
    def __init__(self):
        self.token = None

    def get_token(self, tenant_id, client_id, client_secret):
        url = "https://login.microsoftonline.com/" + tenant_id + "/oauth2/v2.0/token"
        
        values = {
            "client_id" : client_id,
            "scope" : "https://graph.microsoft.com/.default",
            "client_secret" : client_secret,
            "grant_type" : "client_credentials"
        }

        response = requests.post(url, data = values).json()
        try:
            return response["access_token"]
        except KeyError as error:
            print(response["error_description"])
            exit(0)

    def get_data(self, url):
        if self.token:
            finished = False
            results = []
            while True:
                headers = {"Authorization": "Bearer " + self.token}
                response = requests.get(url, headers=headers).json()
                #print(response)
                results = results + response["value"]
                if "@odata.nextLink" in response:
                    url = response["@odata.nextLink"]
                else:
                    break
            return results
        else:
            raise TokenException("No token found. Please call the connect method first.")
            
    def connect(self, tenant_id, client_id, client_secret):
        self.token = self.get_token(tenant_id, client_id, client_secret)
        
    def disconnect(self):
        self.token = None
            
    def get_apps(self):
        if beta_enabled:
            return self.get_data("https://graph.microsoft.com/beta/deviceAppManagement/mobileApps")
        else:
            return self.get_data("https://graph.microsoft.com/v1.0/deviceAppManagement/mobileApps")
    
    def get_app_assignments(self, app_id):
        if beta_enabled:
            return self.get_data("https://graph.microsoft.com/beta/deviceAppManagement/mobileApps/" + app_id + "/assignments")
        else:
            return self.get_data("https://graph.microsoft.com/v1.0/deviceAppManagement/mobileApps/" + app_id + "/assignments")
        
    def get_scripts(self):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/deviceManagementScripts")
    
    def get_script_assignments(self, script_id):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/deviceManagementScripts/" + script_id + "/assignments")
        
    def get_groups(self, starts_with=None):
        if starts_with:
            return self.get_data("https://graph.microsoft.com/v1.0/groups?$filter=startswith(displayName,'" + starts_with + "')")
        else:
            return self.get_data("https://graph.microsoft.com/v1.0/groups")
        
    def get_subgroups(self, group_id):
        members = self.get_data("https://graph.microsoft.com/v1.0/groups/" + group_id + "/members")
        subgroups = []
        for member in members:
            if member["@odata.type"] == "#microsoft.graph.group":
                subgroups = subgroups + [member]
        return subgroups
        
    def get_device_compliance_policies(self):
        return self.get_data("https://graph.microsoft.com/v1.0/deviceManagement/deviceCompliancePolicies")
   
    def get_device_compliance_policy_assignments(self, policy_id):
        return self.get_data("https://graph.microsoft.com/v1.0/deviceManagement/deviceCompliancePolicies/" + policy_id + "/assignments")
        
    def get_configuration_policies(self):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/configurationPolicies")
   
    def get_configuration_policy_assignments(self, policy_id):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/" + policy_id + "/assignments")
        
    def get_group_policies(self):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/groupPolicyConfigurations")
   
    def get_group_policy_assignments(self, policy_id):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/groupPolicyConfigurations/" + policy_id + "/assignments")
        
    def get_device_configuration_profiles(self):
        return self.get_data("https://graph.microsoft.com/v1.0/deviceManagement/deviceConfigurations")
        
    def get_device_configuration_profile_assignments(self, profile_id):
        return self.get_data("https://graph.microsoft.com/v1.0/deviceManagement/deviceConfigurations/" + profile_id + "/assignments")
        
    def get_windows_deployment_profiles(self):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/windowsAutopilotDeploymentProfiles")
        
    def get_windows_deployment_profile_assignments(self, profile_id):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/windowsAutopilotDeploymentProfiles/" + profile_id + "/assignments")
        
    def get_intent_profiles(self):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/intents")
        
    def get_intent_profile_assignments(self, profile_id):
        return self.get_data("https://graph.microsoft.com/beta/deviceManagement/intents/" + profile_id + "/assignments")

class Database:
    def __init__(self, graph_api, db_path):
        self.db = sqlite3.connect(db_path)
        self.api = graph_api
        
    def import_groups(self):
        groups = api.get_groups(starts_with=group_prefix)
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS groups;")
        c.execute("DROP TABLE IF EXISTS memberships;")
        c.execute("CREATE TABLE groups (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE memberships (parent_id TEXT NOT NULL, child_id TEXT NOT NULL);")
        for group in groups:
            c.execute("INSERT INTO groups VALUES (?,?);", (group["id"],group["displayName"]))
            subgroups = api.get_subgroups(group["id"])
            for subgroup in subgroups:
                c.execute("INSERT INTO memberships VALUES (?,?);", (group["id"],subgroup["id"]))
        self.db.commit()
        
    def import_apps(self):
        apps = api.get_apps()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS apps;")
        c.execute("DROP TABLE IF EXISTS app_assignments;")
        c.execute("CREATE TABLE apps (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE app_assignments (app_id TEXT NOT NULL, group_id TEXT NOT NULL, intent TEXT NOT NULL);")
        for app in apps:
            c.execute("INSERT INTO apps VALUES (?,?);", (app["id"],app["displayName"]))
            assignments = api.get_app_assignments(app["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO app_assignments VALUES (?,?,?);", (app["id"],assignment["target"]["groupId"],assignment["intent"]) )
        self.db.commit()
        
    def import_scripts(self):
        scripts = api.get_scripts()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS scripts;")
        c.execute("DROP TABLE IF EXISTS script_assignments;")
        c.execute("CREATE TABLE scripts (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE script_assignments (script_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for script in scripts:
            c.execute("INSERT INTO scripts VALUES (?,?);", (script["id"],script["displayName"]))
            assignments = api.get_script_assignments(script["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO script_assignments VALUES (?,?);", (script["id"],assignment["target"]["groupId"]) )
        self.db.commit()
        
    def import_device_compliance_policies(self):
        policies = api.get_device_compliance_policies()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS device_compliance_policies;")
        c.execute("DROP TABLE IF EXISTS device_compliance_policy_assignments;")
        c.execute("CREATE TABLE device_compliance_policies (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE device_compliance_policy_assignments (policy_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for policy in policies:
            c.execute("INSERT INTO device_compliance_policies VALUES (?,?);", (policy["id"], policy["displayName"]))
            assignments = api.get_device_compliance_policy_assignments(policy["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO device_compliance_policy_assignments VALUES (?,?);", (policy["id"],assignment["target"]["groupId"]) )
        self.db.commit()
        
    def import_configuration_policies(self):
        policies = api.get_configuration_policies()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS configuration_policies;")
        c.execute("DROP TABLE IF EXISTS configuration_policy_assignments;")
        c.execute("CREATE TABLE configuration_policies (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE configuration_policy_assignments (policy_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for policy in policies:
            c.execute("INSERT INTO configuration_policies VALUES (?,?);", (policy["id"], policy["name"]))
            assignments = api.get_configuration_policy_assignments(policy["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO configuration_policy_assignments VALUES (?,?);", (policy["id"],assignment["target"]["groupId"]) )
        self.db.commit()
        
    def import_group_policies(self):
        policies = api.get_group_policies()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS group_policies;")
        c.execute("DROP TABLE IF EXISTS group_policy_assignments;")
        c.execute("CREATE TABLE group_policies (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE group_policy_assignments (policy_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for policy in policies:
            c.execute("INSERT INTO group_policies VALUES (?,?);", (policy["id"], policy["displayName"]))
            assignments = api.get_group_policy_assignments(policy["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO group_policy_assignments VALUES (?,?);", (policy["id"],assignment["target"]["groupId"]) )
        self.db.commit()
        
    def import_device_configuration_profiles(self):
        profiles = api.get_device_configuration_profiles()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS device_configuration_profiles;")
        c.execute("DROP TABLE IF EXISTS device_configuration_profile_assignments;")
        c.execute("CREATE TABLE device_configuration_profiles (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE device_configuration_profile_assignments (profile_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for profile in profiles:
            c.execute("INSERT INTO device_configuration_profiles VALUES (?,?);", (profile["id"], profile["displayName"]))
            assignments = api.get_device_configuration_profile_assignments(profile["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO device_configuration_profile_assignments VALUES (?,?);", (profile["id"],assignment["target"]["groupId"]) )
        self.db.commit()
        
    def import_windows_deployment_profiles(self):
        profiles = api.get_windows_deployment_profiles()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS windows_deployment_profiles;")
        c.execute("DROP TABLE IF EXISTS windows_deployment_profile_assignments;")
        c.execute("CREATE TABLE windows_deployment_profiles (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE windows_deployment_profile_assignments (profile_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for profile in profiles:
            c.execute("INSERT INTO windows_deployment_profiles VALUES (?,?);", (profile["id"], profile["displayName"]))
            assignments = api.get_windows_deployment_profile_assignments(profile["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO windows_deployment_profile_assignments VALUES (?,?);", (profile["id"],assignment["target"]["groupId"]) )
        self.db.commit()

    def import_intent_profiles(self):
        profiles = api.get_intent_profiles()
        c = self.db.cursor()
        c.execute("DROP TABLE IF EXISTS intent_profiles;")
        c.execute("DROP TABLE IF EXISTS intent_profile_assignments;")
        c.execute("CREATE TABLE intent_profiles (id TEXT NOT NULL, display_name TEXT NOT NULL);")
        c.execute("CREATE TABLE intent_profile_assignments (profile_id TEXT NOT NULL, group_id TEXT NOT NULL);")
        for profile in profiles:
            c.execute("INSERT INTO intent_profiles VALUES (?,?);", (profile["id"], profile["displayName"]))
            assignments = api.get_intent_profile_assignments(profile["id"])
            for assignment in assignments:
                if ("target" in assignment) and ("groupId" in assignment["target"]):
                    c.execute("INSERT INTO intent_profile_assignments VALUES (?,?);", (profile["id"],assignment["target"]["groupId"]) )
        self.db.commit()
    
        
    def reload(self):
        self.import_groups()
        self.import_apps()
        self.import_device_compliance_policies()
        self.import_device_configuration_profiles()
        if beta_enabled:
            self.import_windows_deployment_profiles()
            self.import_scripts()
            self.import_configuration_policies()
            self.import_group_policies()
            self.import_intent_profiles()
        
    def get_group_id(self, group_name):
        c = self.db.cursor()
        for row in c.execute("SELECT id FROM groups WHERE display_name = ?;", (group_name,)):
            return row[0]
        return None
        
    def get_group_name(self, group_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM groups WHERE id = ?;", (group_id,)):
            return row[0]
        return "?"
        
    def get_app_name(self, app_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM apps WHERE id = ?;", (app_id,)):
            return row[0]
        return "?"
        
    def get_script_name(self, script_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM scripts WHERE id = ?;", (script_id,)):
            return row[0]
        return "?"
        
    def get_device_compliance_policy_name(self, policy_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM device_compliance_policies WHERE id = ?;", (policy_id,)):
            return row[0]
        return "?"
        
    def get_configuration_policy_name(self, policy_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM configuration_policies WHERE id = ?;", (policy_id,)):
            return row[0]
        return "?"
        
    def get_group_policy_name(self, policy_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM group_policies WHERE id = ?;", (policy_id,)):
            return row[0]
        return "?"
        
    def get_device_configuration_profile_name(self, profile_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM device_configuration_profiles WHERE id = ?;", (profile_id,)):
            return row[0]
        return "?"
    
    def get_windows_deployment_profile_name(self, profile_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM windows_deployment_profiles WHERE id = ?;", (profile_id,)):
            return row[0]
        return "?"
        
    def get_intent_profile_name(self, profile_id):
        c = self.db.cursor()
        for row in c.execute("SELECT display_name FROM intent_profiles WHERE id = ?;", (profile_id,)):
            return row[0]
        return "?"
        
    def get_parent_groups(self, group_id):
        c = self.db.cursor()
        parents = []
        for row in c.execute("SELECT parent_id FROM memberships WHERE child_id = ?;", (group_id,)):
            parents = parents + [row[0]] + self.get_parent_groups(row[0])
        return parents
        
    def print_parent_groups_hierarchy(self, group_id, level):
        c = self.db.cursor()
        for row in c.execute("SELECT parent_id FROM memberships WHERE child_id = ?;", (group_id,)):
            print(level * "-", self.get_group_name(row[0]))
            self.print_parent_groups_hierarchy(row[0], level+1)
        
    def get_child_groups(self, group_id):
        c = self.db.cursor()
        children = []
        for row in c.execute("SELECT child_id FROM memberships WHERE parent_id = ?;", (group_id,)):
            children = children + [row[0]] + self.get_child_groups(row[0])
        return children
        
    def print_child_groups_hierarchy(self, group_id, level):
        c = self.db.cursor()
        for row in c.execute("SELECT child_id FROM memberships WHERE parent_id = ?;", (group_id,)):
            print(level * "-", self.get_group_name(row[0]))
            self.print_child_groups_hierarchy(row[0], level+1)
            
    def get_app_assignments(self, group_id):
        c = self.db.cursor()
        assignments = {}
        for row in c.execute("SELECT app_id, intent FROM app_assignments WHERE group_id = ?",(group_id,)):
            assignments[row[0]] = { "intent": row[1], "group_id" : group_id}
        return assignments
        
    def get_script_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT script_id FROM script_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_device_compliance_policy_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT policy_id FROM device_compliance_policy_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_configuration_policy_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT policy_id FROM configuration_policy_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_group_policy_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT policy_id FROM group_policy_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_device_configuration_profile_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT profile_id FROM device_configuration_profile_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_windows_deployment_profile_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT profile_id FROM windows_deployment_profile_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments
        
    def get_intent_profile_assignments(self, group_id):
        c = self.db.cursor()
        assignments = []
        for row in c.execute("SELECT profile_id FROM intent_profile_assignments WHERE group_id = ?",(group_id,)):
            assignments = assignments + [row[0]]
        return assignments

    def show_group_summary(self, group_name):
        group_id = self.get_group_id(group_name)
        
        if group_id:
            parent_ids = self.get_parent_groups(group_id)
            parent_ids = list(dict.fromkeys(parent_ids)) # Deduplicates ids.
            child_ids = self.get_child_groups(group_id)
            child_ids = list(dict.fromkeys(child_ids)) # Deduplicate ids.
            
            # Show basic group information.
            print("GROUP NAME:\t" + group_name)
            print("ID:\t\t" + group_id)
            print()
            
            # Show parent groups.
            print("=== MEMBER OF ===")
            if len(parent_ids) == 0:
                print("None")
            else:
                self.print_parent_groups_hierarchy(group_id, 1)
            print()
            
            # Show member groups.
            print("=== MEMBERS ===")
            if len(child_ids) == 0:
                print("None")
            else:
                self.print_child_groups_hierarchy(group_id, 1)
            print()
                
            # Show applications.
            print("=== APPLICATIONS ===")
            if not beta_enabled:
                print("(Office, Edge and possibly other 'built-in' apps are not shown, because the beta API is not enabled.)")
            app_assignments = self.get_app_assignments(group_id)
            lines = []
            for app_id in app_assignments:
                line = "- " + self.get_app_name(app_id) + " (" + app_id + ") " + "[" + app_assignments[app_id]["intent"].upper() + "] (directly assigned)"
                lines.append(line)
            for parent_id in parent_ids:
                app_assignments = self.get_app_assignments(parent_id)
                for app_id in app_assignments:
                    line = "- " + self.get_app_name(app_id) + " (" + app_id + ") " + "[" + app_assignments[app_id]["intent"].upper() + "] (via " + self.get_group_name(parent_id) + ")"
                    lines.append(line)
            if len(lines) != 0:
                for line in sorted(lines):
                    print(line)
            else:
                print("None")
            print()
            
            if beta_enabled:
                # Show scripts.
                print("=== SCRIPTS (via beta API) ===")
                script_assignments = self.get_script_assignments(group_id)
                lines = []
                for script_id in script_assignments:
                    line = "- " + self.get_script_name(script_id) + " (" + script_id + ") " + "(directly assigned)"
                    lines.append(line)
                for parent_id in parent_ids:
                    script_assignments = self.get_script_assignments(parent_id)
                    for script_id in script_assignments:
                        line = "- " + self.get_script_name(script_id) + " (" + script_id + ") " + "(via " + self.get_group_name(parent_id) + ")"
                        lines.append(line)
                if len(lines) != 0:
                    for line in sorted(lines):
                        print(line)
                else:
                    print("None")
                print()
                
            # Show device compliance policies.
            print("=== DEVICE COMPLIANCE POLICIES ===")
            assignments = self.get_device_compliance_policy_assignments(group_id)
            lines = []
            for policy_id in assignments:
                line = "- " + self.get_device_compliance_policy_name(policy_id) + " (" + policy_id + ")" + " (directly assigned)"
                lines.append(line)
            for parent_id in parent_ids:
                assignments = self.get_device_compliance_policy_assignments(parent_id)
                for policy_id in assignments:
                    line = "- " + self.get_device_compliance_policy_name(policy_id) + " (" + policy_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                    lines.append(line)
            if len(lines) != 0:
                for line in sorted(lines):
                    print(line)
            else:
                print("None")
            print()
            
            # Show configuration policies.
            if beta_enabled:
                print("=== CONFIGURATION POLICIES (via beta API) ===")
                assignments = self.get_configuration_policy_assignments(group_id)
                lines = []
                for policy_id in assignments:
                    line = "- " + self.get_configuration_policy_name(policy_id) + " (" + policy_id + ")" + " (directly assigned)"
                    lines.append(line)
                for parent_id in parent_ids:
                    assignments = self.get_configuration_policy_assignments(parent_id)
                    for policy_id in assignments:
                        line = "- " + self.get_configuration_policy_name(policy_id) + " (" + policy_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                        lines.append(line)
                if len(lines) != 0:
                    for line in sorted(lines):
                        print(line)
                else:
                    print("None")
                print()
                
            # Show configuration policies.
            if beta_enabled:
                print("=== GROUP POLICIES (via beta API) ===")
                assignments = self.get_group_policy_assignments(group_id)
                lines = []
                for policy_id in assignments:
                    line = "- " + self.get_group_policy_name(policy_id) + " (" + policy_id + ")" + " (directly assigned)"
                    lines.append(line)
                for parent_id in parent_ids:
                    assignments = self.get_group_policy_assignments(parent_id)
                    for policy_id in assignments:
                        line = "- " + self.get_group_policy_name(policy_id) + " (" + policy_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                        lines.append(line)
                if len(lines) != 0:
                    for line in sorted(lines):
                        print(line)
                else:
                    print("None")
                print()
            
            # Show device configuration profiles.
            print("=== DEVICE CONFIGURATION PROFILES ===")
            assignments = self.get_device_configuration_profile_assignments(group_id)
            lines = []
            for profile_id in assignments:
                line = "- " + self.get_device_configuration_profile_name(profile_id) + " (" + profile_id + ")" + " (directly assigned)"
                lines.append(line)
            for parent_id in parent_ids:
                assignments = self.get_device_configuration_profile_assignments(parent_id)
                for profile_id in assignments:
                    line = "- " + self.get_device_configuration_profile_name(profile_id) + " (" + profile_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                    lines.append(line)
            if len(lines) != 0:
                for line in sorted(lines):
                    print(line)
            else:
                print("None")
            print()

            # Show intent profiles.
            if beta_enabled:
                print("=== INTENT PROFILES (via beta API) ===")
                assignments = self.get_intent_profile_assignments(group_id)
                lines = []
                for profile_id in assignments:
                    line = "- " + self.get_intent_profile_name(profile_id) + " (" + profile_id + ")" + " (directly assigned)"
                    lines.append(line)
                for parent_id in parent_ids:
                    assignments = self.get_intent_profile_assignments(parent_id)
                    for profile_id in assignments:
                        line = "- " + self.get_intent_profile_name(profile_id) + " (" + profile_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                        lines.append(line)
                if len(lines) != 0:
                    for line in sorted(lines):
                        print(line)
                else:
                    print("None")
                print()

            # Show windows deployment profiles.
            if beta_enabled:
                print("=== WINDOWS DEPLOYMENT PROFILES (via beta API) ===")
                assignments = self.get_windows_deployment_profile_assignments(group_id)
                lines = []
                for profile_id in assignments:
                    line = "- " + self.get_windows_deployment_profile_name(profile_id) + " (" + profile_id + ")" + " (directly assigned)"
                    lines.append(line)
                for parent_id in parent_ids:
                    assignments = self.get_windows_deployment_profile_assignments(parent_id)
                    for profile_id in assignments:
                        line = "- " + self.get_windows_deployment_profile_name(profile_id) + " (" + profile_id + ")" + " (via " + self.get_group_name(parent_id) + ")"
                        lines.append(line)
                if len(lines) != 0:
                    for line in sorted(lines):
                        print(line)
                else:
                    print("None")
                print()
            
parser = argparse.ArgumentParser(description='See what Intune components are linked to AD groups.')
parser.add_argument("group_name", help="The group you want to get info about.")
parser.add_argument("--reload", dest="reload", action="store_true", help="Refresh the cached data from Azure Graph API to get an up-to-date view. This can take a few minutes.")
parser.set_defaults(reload=False)

arguments = parser.parse_args()
group_name = arguments.group_name
reload = arguments.reload

if not os.path.isfile(cache_database_path):
    reload = True

api = GraphAPI()
api.connect(tenant_id, client_id, client_secret)
db = Database(api, cache_database_path)

if reload:
    db.reload()
db.show_group_summary(group_name)

