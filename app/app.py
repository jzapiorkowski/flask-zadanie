from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import json

app = Flask(__name__)

load_dotenv()

uri = os.getenv('URI')
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

driver = GraphDatabase.driver(uri, auth=(username, password), database="neo4j")
session = driver.session()

def get_employees(tx, name, position, sort):
    query = "MATCH (employee: Employee)"

    conditions = []

    if name is not None:
        conditions.append(f"employee.name CONTAINS '{name}'")
    if position is not None:
        conditions.append(f"employee.position CONTAINS '{position}'")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " RETURN employee"

    if sort == "name_asc":
        query += " ORDER BY employee.name"
    else:
        query += " ORDER BY employee.name DESC"
    
    results = tx.run(query).data()

    return results


def create_employee(tx, name, position, department, relation):
    # existing_employee = tx.run(f"""MATCH (employee:Employee {{ name: '{name}' }}) 
    #                  RETURN employee""").data()

    query = f"""MATCH (department:Department {{ name: '{department}' }}) 
                CREATE (employee:Employee {{ name: '{name}', position: '{position}'}}) -[:{relation}]-> (department) 
                    RETURN employee"""
    tx.run(query)


def update_employee(tx, id, name, position, department):
    query = f"MATCH (employee: Employee) WHERE ID(employee) = {id} SET"
    to_update = []

    if name is not None:
        to_update.append(f" employee.name = '{name}'")
    if position is not None:
        to_update.append(f" employee.position = '{position}'")
    if department is not None:
        to_update.append(f" employee.department = '{department}'")
    
    query += ", ".join(to_update)

    tx.run(query)

    return {"message": "success"}

def delete_employee(tx, id, department_name):
    if department_name is not None:
        query = f"""MATCH (employee: Employee)-[manages:MANAGES]->(department:Department)
                WHERE ID(employee) = {id}
                DETACH DELETE employee, department"""
    else:
        query = f"MATCH (employee: Employee) WHERE ID(employee) = {id} DETACH DELETE employee"

    tx.run(query)

def get_departments(tx, name, sort):
    query = "MATCH (employee:Employee)-[relation]->(department:Department)"

    conditions = []

    if name is not None:
        query += f" WHERE department.name CONTAINS {name}"

    query += " RETURN department.name, count(relation) as number_of_employees,  ID(department)"

    if sort == "name_asc":
        query += " ORDER BY d.name"
    elif sort == "name_desc":
        query += " ORDER BY d.name DESC"
    elif sort == "employees_asc":
        query += " ORDER BY number_of_employees"
    elif sort == "employees_desc":
        query += " ORDER BY number_of_employees DESC"

    results = tx.run(query).data()

    return results

def get_department_employees(tx, id):
    query = f"""MATCH (department:Department) 
                WHERE id(department) = {id} 
                RETURN department"""
    results = tx.run(query).data()

    if not results:
        return None

    query = f"""MATCH (department:Department) <-[:WORKS_IN]- (employee:Employee) 
                WHERE id(department) = {id}
                RETURN employee"""

    employees = tx.run(query).data()

    return employees


@app.route("/employees", methods=["GET"])
def get_employees_route():
    try:
        name = request.args.get("name", default=None)
        position = request.args.get("position", default=None)
        sort = request.args.get("sort", default='name_asc')

        employees = driver.session().execute_write(get_employees, name, position, sort)

        return jsonify(employees)

    except Exception as error:
        return str(error)

@app.route('/employees', methods=["POST"])
def create_employee_route():
    try:
        name = request.json['name']
        position = request.json['position']
        department = request.json['department']
        relation = request.json['relation']

        driver.session().execute_write(create_employee, name, position, department, relation)

        return jsonify({'message': 'success'})

    except Exception as error:
        return str(error)

@app.route('/employees/<int:id>', methods=['PUT'])
def update_employee_route(id):
    try:
        name = request.json.get('name')
        role = request.json.get('role')
        department = request.json.get('department')

        if name is None and role is None and department is None:
            return jsonify({'message': 'no data to update'})

        res = driver.session().run(f"MATCH (employee:Employee) WHERE ID(employee) = {id} RETURN employee").single()

        if res is None:
            return jsonify({"error": "Employee not found."})

        result = session.execute_write(update_employee, id, name, role, department)

        return jsonify(result)
    except Exception as error:
        return str(error)


@app.route('/employees/<int:id>', methods=['DELETE'])
def delete_employee_route(id):
    try:
        result = driver.session().run(f"MATCH (employee:Employee) WHERE ID(employee) = {id} RETURN COUNT(employee) as count").single()

        if result["count"] == 0:
            return jsonify({"error": "Employee not found."})

        result = driver.session().run(f"""MATCH (employee:Employee)-[manages:MANAGES]->(department:Department)"
                             " WHERE ID(eemployee) = {id} RETURN department.name""").single()

        if result is None:
            session.execute_write(delete_employee, id)

            return jsonify({"message": "Employee deleted successfully"})
        else:
            department_name = result["d.name"]
            session.execute_write(delete_employee, id, department_name)

            return jsonify({"message": "Deleted employee and their department"})
    except Exception as error:
        return str(error)



@app.route('/employees/<int:id>/subordinates', methods=['GET'])
def get_subordinates_route(id):
    try:
        result = driver.session().run(f"""MATCH (manager:Employee)-[manages:MANAGES]->(department:Department) WHERE ID(manager) = {id}
                             RETURN department.name""").single()
        if not result:
            return jsonify({"error": "Employee or department not found"})

        department_name = result["department_name"]

        query = f"""MATCH (employee:Employee)-[works_in:WORKS_IN]->(department:Department)
                WHERE department.name = {department_name} RETURN employee.name"""

        results = driver.session().run(query).data()

        subordinates = [{"name": result["name"]} for result in results]

        return jsonify(subordinates)

    except Exception as error:
        return str(error)


@app.route('/departments', methods=['GET'])
def get_departments_route():
    try:
        name = request.args.get('name')
        sort = request.args.get('sort')

        departments = driver.session().read_transaction(get_departments, name, sort)

        return jsonify(departments)
    except Exception as error:
        return str(error)


@app.route('/departments/<id>/employees', methods=['GET'])
def get_department_employees_route(id):

    employees = driver.session().execute_read(get_department_employees, id)

    if not employees:
        return jsonify({'message': 'Department not found'})

    return jsonify({'employees': employees})


if __name__ == '__main__':
    app.run()