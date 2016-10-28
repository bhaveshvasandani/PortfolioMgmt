# Copyright 2016 John J. Rofrano. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import redis
from flask import Flask, Response, jsonify, request, json

# Status Codes
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_204_NO_CONTENT = 204
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409

# Create Flask application
app = Flask(__name__)

database = {
            0 : ["commodity", "gold", 1286.59],
            1 : ["real-estate", "NYC real estate index", 16255.18],
            2 : ["commodity", "brent crude oil", 51.45],
            3 : ["fixed income", "US 10Y T-Note", 130.77]
            }
            
class NegativeAssetException(Exception):
    pass
    
class AssetNotFoundException(Exception):
    pass

class Asset(object):
    def __init__(self, id, quantity = 0):
        self.id = int(id)
        self.asset_class = database[self.id][0]
        self.name = database[self.id][1]
        self.price = database[self.id][2]
        self.quantity = quantity
        self.nav = self.quantity * self.price
        
    def buy(self, Q):
        self.quantity += Q
        self.nav = self.quantity * self.price
        
    def sell(self, Q):
        if self.quantity - Q < 0:
            raise NegativeAssetException()
        self.quantity -= Q
        self.nav = self.quantity * self.price
        
    def serialize(id):
        #This generates a string from the Asset object (id, quantity parameters)
        id_hex = str(id).encode("hex")
        q_hex = str(self.quantity).encode("hex")
        serialized_data = id_hex + ";" + q_hex
        return serialized_data
    
    @staticmethod
    def deserialize(serialized_data):
        #This takes the string generated from serialize and returns an Asset object
        serialized_data = serialized_data.split(";")
        id = serialized_data[0].decode("hex")
        q = serialized_data[1].decode("hex")
        return Asset(id, q)
        


class Portfolio(object):
    def __init__(self, user): #constructor
        self.user = str(user) #only used to serialize and deserialize
        self.assets = dict()
        self.nav = 0
       
    def buy(self, id, Q): #This also creates new asset in the portfolio
        if Q == 0:
            return
        try:
            asset = self.assets[id]
        except KeyError: # Asset was not present in portfolio
            asset = Asset(id, Q)
            self.assets[id] = asset
        else: # Asset was present in portfolio
            self.assets[id].buy(Q)
        self.nav += self.assets[id].price * Q 
        
    def sell(self, id, Q):
        if Q == 0:
            return
        try:
            asset = self.assets[id]
        except KeyError: # Asset was not present in portfolio
            raise AssetNotFoundException()
        else:
            self.assets[id].sell(Q) #raises an error if q becomes negative
            self.nav -= self.assets[id].price * Q
            if self.assets[id].quantity == 0:
                del self.assets[id]
        
    def buy_sell(self, id, Q):
        if Q < 0:
            self.sell(id, -Q)
        else:
            self.buy(id, Q)
        
    def remove_asset(self, id):
        del self.assets[id]
        
    def json_serialize(self, user, url_root):
        return {
            "user" : user,
            "numberOfAssets" : len(self.assets),
            "netAssetValue" : self.nav,
            "links" : create_links_for_portfolio(self, url_root)
        }
        
    def serialize():
        #This generates a string from the Portfolio object (user, and assets parameters)
        user_hex = self.user.encode("hex")
        assets = "#".join([a.serialize(a_id) for a_id, a in assets.iteritems()])
        assets_hex = assets.encode("hex")        
        serialized_data = user_hex + ";" + assets_hex
        return serialized_data
    
    @staticmethod
    def deserialize(serialized_data):
        #This takes the string generated from serialize and returns a Portfolio object
        serialized_data = serialized_data.split(";")
        user = serialized_data[0].decode("hex")
        p = Portfolio(user)
        assets_str = serialized_data[1].decode("hex").split("#")
        assets_lst = [deserialize(asset_str) for asset_str in assets_str]
        for asset in assets_lst:
            p.assets[asset.id] = asset
            p.nav += asset.quantity * asset.price
        return p
        
portfolios = dict()

######################################################################
# GET INDEX
######################################################################
@app.route('/')
def index():
    return app.send_static_file('index.html')

######################################################################
# LIST ALL portfolios
######################################################################
@app.route('/api/v1/portfolios', methods=['GET'])
def list_portfolios():
    """
    GET request at /api/v1/portfolios
    
    Returns all portfolios with form
    {
        "portfolios" : [
            "user" : <user>
            "numberOfAssets" : <number of assets>
            "netAssetValue : <nav>
            "links" : [
                "rel" : "self"
                "href" : <fully-fledged url to list_assets(<user>)>
            ]
        ]...
    }
    """
    portfolios_array = []
    for user, portfolio in portfolios.iteritems():
        json_data = portfolio.json_serialize(user, request.url_root)
        portfolios_array.append(json_data)
    return reply({"portfolios" : portfolios_array}, HTTP_200_OK)

######################################################################
# LIST ALL assets of a user
######################################################################
@app.route('/api/v1/portfolios/<user>', methods=['GET'])
def list_assets(user):
    """
    GET request at localhost:5000/api/v1/portfolios/<user>
    """
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply({'error' : 'User {0} not found'.format(user)}, HTTP_404_NOT_FOUND)
    return reply({'assets' : [asset.name for asset in portfolios[user].assets.itervalues()]}, HTTP_200_OK)
    
######################################################################
# RETRIEVE the quantity and total value of an asset in a portfolio
######################################################################
@app.route('/api/v1/portfolios/<user>/<asset_id>', methods=['GET'])
def get_asset(user, asset_id):
    """
    GET request at localhost:5000/api/v1/portfolios/<user>/<asset_id>
    """
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply({'error' : 'User {0} not found'.format(user)}, HTTP_404_NOT_FOUND)
    try:
        asset = portfolio.assets[asset_id]
    except KeyError:
        return reply({'error' : 'Asset with id %s does not exist in this portfolio' % asset_id }, HTTP_404_NOT_FOUND)
    return reply({'quantity' : asset.quantity, 'value' : asset.nav}, HTTP_200_OK)
        

######################################################################
# RETRIEVE the NAV of a portfolio
######################################################################
@app.route('/api/v1/portfolios/<user>/nav', methods=['GET'])
def get_nav(user):
    """
    GET request at localhost:5000/api/v1/portfolios/<user>/nav
    """
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply({'error' : 'User {0} not found'.format(user)}, HTTP_404_NOT_FOUND)
    return reply({"nav" : portfolio.nav}, HTTP_200_OK)

######################################################################
# ADD A NEW user portfolio
######################################################################
@app.route('/api/v1/portfolios', methods=['POST'])
def create_user():
    """
    POST request at localhost:5000/api/v1/portfolios with this body:
    {
        "user": "john"
    }
    """
    try:
        payload = json.loads(request.data)
    except ValueError:
        return reply({'error' : 'Data %s is not valid' % request.data}, HTTP_400_BAD_REQUEST)
    if not is_valid(payload, ['user']):
        return reply({'error' : 'Payload %s is not valid' % payload}, HTTP_400_BAD_REQUEST)
    user = payload['user']
    try:
        portfolio = portfolios[user]
    except KeyError:
        portfolios[user] = Portfolio(user)
        return reply("",HTTP_201_CREATED)
    return reply({'error' : 'User {0} already exists'.format(user)}, HTTP_409_CONFLICT)

######################################################################
# ADD A NEW asset
######################################################################
@app.route('/api/v1/portfolios/<user>', methods=['POST'])
def create_asset(user):
    """
    POST request at localhost:5000/api/v1/portfolios/<user> with this body:
    {
        "asset_id": 2,
        "quantity": 10
    }
    """
    try:
        payload = json.loads(request.data)
    except ValueError:
        return reply({'error' : 'Data %s is not valid' % request.data}, HTTP_400_BAD_REQUEST)
    if not is_valid(payload, ['asset_id','quantity']):
        return reply({'error' : 'Payload %s is not valid' % payload}, HTTP_400_BAD_REQUEST)
    asset_id = int(payload['asset_id'])
    quantity = int(payload['quantity'])
    if asset_id not in database: #asset_id exists and is associated
        return reply({'error' : 'Asset id %s does not exist in database' % asset_id}, HTTP_400_BAD_REQUEST)
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply({'error' : 'User {0} not found'.format(user)}, HTTP_404_NOT_FOUND)
    portfolios[user].buy(asset_id, quantity) #That would act as a PUT in some cases, is this fine ? XXX should be error 409 ?
    return reply("", HTTP_201_CREATED)

######################################################################
# UPDATE AN EXISTING resource
######################################################################
@app.route('/api/v1/portfolios/<user>/<asset_id>', methods=['PUT'])
def update_asset(user, asset_id):
    try:
        payload = json.loads(request.data)
    except ValueError:
        return reply({'error' : 'Data %s is not valid' % request.data}, HTTP_400_BAD_REQUEST)
    if not is_valid(payload, ['quantity']):
        return reply({'error' : 'Payload %s is not valid' % payload}, HTTP_400_BAD_REQUEST)
    asset_id = int(asset_id)
    quantity = int(payload['quantity'])
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply({'error' : 'User {0} not found'.format(user)}, HTTP_404_NOT_FOUND)
    try:
        portfolios[user].buy_sell(asset_id, quantity)
    except AssetNotFoundException:
        return reply({'error' : 'Asset with id {0} was not found in the portfolio of {1}.'.format(asset_id, user)}, HTTP_404_NOT_FOUND)
    except NegativeAssetException:
        return reply({'error' : 'Selling {0} units of the asset with id {1} in the portfolio of {2} would result in a negative quantity. The operation was aborted.'.format(-quantity, asset_id, user)}, HTTP_400_BAD_REQUEST)
    return reply("", HTTP_200_OK)

######################################################################
# DELETE an asset from a user's portfolio
######################################################################
@app.route('/api/v1/portfolios/<user>/<asset_id>', methods=['DELETE'])
def delete_asset(user, asset_id):
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply("", HTTP_204_NO_CONTENT)
    portfolios[user].remove_asset(int(asset_id)) #removes or does nothing if no asset
    return reply("", HTTP_204_NO_CONTENT)

######################################################################
# DELETE a user (or its portfolio)
######################################################################
@app.route('/api/v1/portfolios/<user>', methods=['DELETE'])
def delete_user(user):
    try:
        portfolio = portfolios[user]
    except KeyError:
        return reply("", HTTP_204_NO_CONTENT)
    portfolios.remove(portfolio)
    return reply("", HTTP_204_NO_CONTENT)


######################################################################
# UTILITY FUNCTIONS
######################################################################
def create_links_for_portfolio(portfolio, url_root):
    return [
        {
            "rel" : "self",
            "href" : url_root + "api/v1/portfolios/" + portfolio.user
        }
    ]
    
def reply(message, rc):
    response = jsonify(message) #or jsonify?
    response.headers['Content-Type'] = 'application/json'
    response.status_code = rc
    return response
    
def is_valid(data, keys=[]):
    valid = False
    try:
        for k in keys:
            _temp = data[k]
        valid = True
    except KeyError as e:
        app.logger.error('Missing value error: %s', e)
    return valid


######################################################################
#   M A I N
######################################################################
if __name__ == "__main__":
    # Get bindings from the environment
    port = os.getenv('PORT', '5000')
    hostname = os.getenv('HOSTNAME','127.0.0.1')
    redis_port = os.getenv('REDIS_PORT','6379')
    redis_server = redis.Redis(host=hostname, port=int(redis_port))
    app.run(host='0.0.0.0', port=int(port), debug=True)
