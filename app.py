import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, IntegerField, TextAreaField
from wtforms.validators import InputRequired, Length, ValidationError
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask_wtf.csrf import CSRFProtect

# =======================
# CONFIG APP
# =======================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

vietnam_tz = timezone(timedelta(hours=7))

# =======================
# SELLER REQUIRED DECORATOR
# =======================
def seller_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'seller':
            abort(403)
        return f(*args, **kwargs)
    return decorated

# =======================
# LOAD USER
# =======================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =======================
# DATABASE MODELS
# =======================
class User(db.Model, UserMixin):
    id               = db.Column(db.Integer, primary_key=True)
    username         = db.Column(db.String(20), unique=True, nullable=False)
    password_nothash = db.Column(db.String(200), nullable=False)
    password         = db.Column(db.String(200), nullable=False)
    role             = db.Column(db.String(10), nullable=False)
    phone            = db.Column(db.String(20))
    address          = db.Column(db.String(200))

class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100))
    price       = db.Column(db.Integer)
    image       = db.Column(db.String(200))
    description = db.Column(db.String(300))
    seller_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    seller      = db.relationship('User', backref='products')

class CartItem(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity   = db.Column(db.Integer, default=1, nullable=False)
    product    = db.relationship('Product', backref='cart_items')

class Order(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name  = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), nullable=False)
    address    = db.Column(db.String(200), nullable=False)
    total      = db.Column(db.Integer, nullable=False)
    status     = db.Column(db.String(20), nullable=False, server_default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(vietnam_tz))
    items      = db.relationship('OrderItem', backref='order', lazy=True)
    user       = db.relationship('User', backref='orders')

class OrderItem(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    price        = db.Column(db.Integer, nullable=False)
    quantity     = db.Column(db.Integer, nullable=False)
    seller_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Feedback(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(20), nullable=False)
    description  = db.Column(db.String(200), nullable=False)

    
# =======================
# FORMS
# =======================
class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[InputRequired(), Length(min=4, max=20)])
    password = PasswordField("Password", validators=[InputRequired(), Length(min=4, max=20)])
    role     = SelectField("Account type", choices=[("user","User"),("seller","Seller")])
    phone    = StringField("Phone")
    address  = StringField("Address")
    submit   = SubmitField("Register")

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError("Username already exists")

    def validate_phone(self, phone):
        if self.role.data == "seller" and phone.data == "":
            raise ValidationError("Sellers must enter a phone number.")
        if User.query.filter_by(phone=phone.data).first():
            raise ValidationError("Phone already exists")

    def validate_address(self, address):
        if self.role.data == "seller" and address.data == "":
            raise ValidationError("Seller must enter an address.")

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[InputRequired()])
    password = PasswordField("Password", validators=[InputRequired()])
    submit   = SubmitField("Login")

class ProductForm(FlaskForm):
    name        = StringField("Product Name", validators=[InputRequired(), Length(max=100)])
    price       = IntegerField("Price (₫)", validators=[InputRequired()])
    image       = StringField("Image URL", validators=[InputRequired()])
    description = TextAreaField("Description", validators=[InputRequired(), Length(max=300)])
    submit      = SubmitField("Save Product")

class FeedbackForm(FlaskForm):
    description = TextAreaField("Feedback", validators=[InputRequired(), Length(max=300)])


# =======================
# ROUTES — BUYER
# =======================

@app.route("/")
def home():
    products = Product.query.all()
    return render_template("home.html", products=products)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product_detail.html", product=product)

@app.route("/register", methods=["GET","POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        new_user = User(
            username=form.username.data,
            password_nothash=form.password.data,
            password=hashed_pw,
            role=form.role.data,
            phone=form.phone.data,
            address=form.address.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            if bcrypt.check_password_hash(user.password, form.password.data):
                login_user(user)
                flash("Login successful!")
                next_page = request.args.get('next')
                return redirect(next_page or url_for("home"))
            else:
                flash("Incorrect password")
        else:
            flash("No account exists.")
    return render_template("login.html", form=form)

@app.route("/feedback")
@login_required
def feedback():
    form = FeedbackForm()
    return render_template("feedback.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Already logged out")
    return redirect(url_for("login"))

# =======================
# ROUTES — CART
# =======================

@app.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(i.product.price * i.quantity for i in items)
    return render_template("cart.html", items=items, total=total)

@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    if not current_user.is_authenticated:
        flash("Please log in to add items to your cart.")
        return redirect(url_for("login", next=request.referrer))
    item = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if item:
        item.quantity += 1
    else:
        item = CartItem(user_id=current_user.id, product_id=product_id)
        db.session.add(item)
    db.session.commit()
    flash("Added to cart!")
    return redirect(request.referrer or "/")

@app.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    qty = int(request.form.get("quantity", 1))
    if qty <= 0:
        db.session.delete(item)
    else:
        item.quantity = qty
    db.session.commit()
    return redirect(url_for("cart"))

@app.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash("The product has been removed.")
    return redirect(url_for("cart"))

# =======================
# ROUTES — CHECKOUT
# =======================

@app.route("/checkout")
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("The shopping cart is empty!")
        return redirect(url_for("cart"))
    total = sum(i.product.price * i.quantity for i in items)
    return render_template("checkout.html", items=items, total=total)

@app.route("/checkout/place", methods=["POST"])
@login_required
def place_order():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("The shopping cart is empty!")
        return redirect(url_for("cart"))

    total = sum(i.product.price * i.quantity for i in items)

    order = Order(
        user_id   = current_user.id,
        full_name = request.form.get("full_name"),
        phone     = request.form.get("phone"),
        address   = request.form.get("address"),
        total     = total,
        status    = 'pending'
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        order_item = OrderItem(
            order_id     = order.id,
            product_id   = item.product_id,
            product_name = item.product.name,
            price        = item.product.price,
            quantity     = item.quantity,
            seller_id    = item.product.seller_id
        )
        db.session.add(order_item)

    CartItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()

    flash("Order placed successfully!")
    return redirect(url_for("order_detail", order_id=order.id))

@app.route("/orders")
@login_required
def orders():
    my_orders = Order.query.filter_by(user_id=current_user.id)\
                           .order_by(Order.created_at.desc()).all()
    return render_template("orders.html", orders=my_orders)

@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        abort(403)
    return render_template("order_detail.html", order=order)

# =======================
# ROUTES — SELLER DASHBOARD
# =======================

@app.route("/seller")
@login_required
@seller_required
def seller_dashboard():
    seller_orders = db.session.query(Order)\
        .join(OrderItem, Order.id == OrderItem.order_id)\
        .filter(OrderItem.seller_id == current_user.id)\
        .order_by(Order.created_at.desc())\
        .distinct().all()

    my_products = Product.query.filter_by(seller_id=current_user.id).all()

    total_revenue = db.session.query(
        db.func.sum(OrderItem.price * OrderItem.quantity)
    ).filter(OrderItem.seller_id == current_user.id).scalar() or 0

    return render_template("seller/dashboard.html",
                           orders=seller_orders,
                           products=my_products,
                           total_revenue=total_revenue)

@app.route("/seller/products")
@login_required
@seller_required
def seller_products():
    my_products = Product.query.filter_by(seller_id=current_user.id).all()
    return render_template("seller/products.html", products=my_products)

@app.route("/seller/products/add", methods=["GET","POST"])
@login_required
@seller_required
def seller_add_product():
    form = ProductForm()
    if form.validate_on_submit():
        product = Product(
            name        = form.name.data,
            price       = form.price.data,
            image       = form.image.data,
            description = form.description.data,
            seller_id   = current_user.id
        )
        db.session.add(product)
        db.session.commit()
        flash("The product has been added!")
        return redirect(url_for("seller_products"))
    return render_template("seller/product_form.html", form=form, title="Add Product")

@app.route("/seller/products/edit/<int:product_id>", methods=["GET","POST"])
@login_required
@seller_required
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        abort(403)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        product.name        = form.name.data
        product.price       = form.price.data
        product.image       = form.image.data
        product.description = form.description.data
        db.session.commit()
        flash("The product has been updated!")
        return redirect(url_for("seller_products"))
    return render_template("seller/product_form.html", form=form, title="Edit Product")

@app.route("/seller/products/delete/<int:product_id>", methods=["POST"])
@login_required
@seller_required
def seller_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    flash("The product has been removed.")
    return redirect(url_for("seller_products"))

@app.route("/seller/orders")
@login_required
@seller_required
def seller_orders():
    seller_orders = db.session.query(Order)\
        .join(OrderItem, Order.id == OrderItem.order_id)\
        .filter(OrderItem.seller_id == current_user.id)\
        .order_by(Order.created_at.desc())\
        .distinct().all()
    return render_template("seller/orders.html", orders=seller_orders)

@app.route("/seller/orders/<int:order_id>")
@login_required
@seller_required
def seller_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    my_items = OrderItem.query.filter_by(order_id=order_id, seller_id=current_user.id).all()
    my_total = sum(i.price * i.quantity for i in my_items)
    return render_template("seller/order_detail.html", order=order, items=my_items, my_total=my_total)

@app.route("/seller/orders/update/<int:order_id>", methods=["POST"])
@login_required
@seller_required
def seller_update_order(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")
    if new_status in ["pending", "confirmed", "shipping", "delivered", "cancelled"]:
        order.status = new_status
        db.session.commit()
        flash("Order status updated successfully!")
    return redirect(url_for("seller_order_detail", order_id=order_id))

# =======================
# RUN APP
# =======================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if Product.query.count() == 0:
            p1 = Product(
                name="Iphone 15",
                price=25000000,
                description="Điện thoại Apple mới nhất",
                image="https://cdn.tgdd.vn/Products/Images/42/303891/iphone-15-pro-max-blue-thumbnew-600x600.jpg"
            )
            p2 = Product(
                name="Laptop Gaming",
                price=20000000,
                description="Laptop chơi game siêu mạnh",
                image="https://product.hstatic.net/200000722513/product/asus_tuf_gaming_f15_fx507_1_9f9f0b2d6aaf4f0c9f5f4f0b2d6aaf4f.png"
            )
            db.session.add(p1)
            db.session.add(p2)
            db.session.commit()
    app.run()
    # app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
