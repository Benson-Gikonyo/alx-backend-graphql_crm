import re
import graphene
from graphene_django import DjangoObjectType
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Customer, Order, Product
from decimal import Decimal as D
import datetime


# inputs
class CustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class ProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Decimal(required=True)
    stock = graphene.Int()


class OrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime()


# Object types:
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")


# mutations:
class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = graphene.Argument(CustomerInput, required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, input):
        # Extract fields from input
        name = input.name
        email = input.email
        phone = input.phone

        if Customer.objects.filter(email=email).exists():
            raise ValidationError("Email already exists.")

        if phone and not re.match(r"^\+?\d{7,15}$|^\d{3}-\d{3}-\d{4}$", phone):
            raise ValidationError(
                "Invalid phone format. Use +1234567890 or 123-456-7890"
            )

        customer = Customer.objects.create(name=name, email=email, phone=phone or "")

        return CreateCustomer(
            customer=customer, message="Customer created successfully"
        )


class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    @classmethod
    def mutate(cls, root, info, input):
        created_customers = []
        errors = []

        if not input:
            return BulkCreateCustomers(customers=[], errors=["No customers provided"])

        with transaction.atomic():
            for data in input:
                try:
                    # Validate unique email
                    if Customer.objects.filter(email=data.email).exists():
                        errors.append(f"Email '{data.email}' already exists")
                        continue

                    customer = Customer.objects.create(
                        name=data.name,
                        email=data.email,
                        phone=data.phone or "",
                    )
                    created_customers.append(customer)

                except Exception as e:
                    errors.append(
                        f"Error creating {getattr(data, 'email', '')}: {str(e)}"
                    )

        return BulkCreateCustomers(customers=created_customers, errors=errors)


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)

    product = graphene.Field(ProductType)
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, input):
        price = D(input.price)
        if price <= 0:
            raise Exception("Price must be positive")
        if input.stock < 0:
            raise Exception("Stock cannot be negative")

        product = Product.objects.create(
            name=input.name, price=price, stock=input.stock or 0
        )
        return CreateProduct(product=product, message="Product created successfully")


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = OrderInput(required=True)

    order = graphene.Field(OrderType)
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, input):
        # Extract input values
        customer_id = input.customer_id
        product_ids = input.product_ids
        order_date = input.order_date

        # Validate customer
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            raise Exception(f"Customer ID {customer_id} does not exist")

        # Validate products
        if not product_ids:
            raise Exception("At least one product must be selected.")

        products = []
        total_amount = D("0")
        for pid in product_ids:
            try:
                product = Product.objects.get(id=pid)
                products.append(product)
                total_amount += D(product.price)
            except Product.DoesNotExist:
                raise Exception(f"Product ID {pid} does not exist")

        # Create order
        order = Order.objects.create(
            customer=customer,
            total_amount=total_amount,
            order_date=order_date or datetime.datetime.now(),
        )
        order.products.set(products)

        return CreateOrder(order=order, message="Order created successfully!")


# Schema definition
class Query(graphene.ObjectType):
    all_customers = graphene.List(CustomerType)
    all_products = graphene.List(ProductType)
    all_orders = graphene.List(OrderType)

    def resolve_all_customers(root, info):
        return Customer.objects.all()

    def resolve_all_products(root, info):
        return Product.objects.all()

    def resolve_all_orders(root, info):
        return Order.objects.all()


class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
