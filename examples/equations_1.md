![](images/page_0_figure_1.jpeg)

A connected algebraic set with two irreducible components.

COROLLARY 2.32. *The radical of an ideal*  $a$  *in*  $k[X\_1, ..., X\_n]$  *is a finite intersection of prime ideals,*  $rad(a) = p\_1 \cap ... \cap p\_n$ . *If there are no inclusions among the*  $p\_i$ , *then the*  $p\_i$  *are uniquely determined up to order (and they are exactly the minimal prime ideals containing* a).

PROOF. Write  $V(a)$  as a union of its irreducible components,  $V(a) = \bigcup\_{i=1}^{n} V\_i$ , and let  $p\_i = I(V\_i)$ . Then  $rad(a) = p\_1 \cap ... \cap p\_n$  because they are both radical ideals and

$$V(\text{rad}(\mathfrak{a})) = V(\mathfrak{a}) = \bigcup V(\mathfrak{p}\_l) \stackrel{2.10b}{=} V(\bigcap\_l \mathfrak{p}).$$

The uniqueness similarly follows from the proposition. <sup>2</sup>

## *Remarks*

An irreducible topological space is connected, but a connected topological space need not be irreducible. For example, the union of two surfaces in 3-space intersecting along a curve is reducible, but connected.

2.33. An algebraic subset  $V$  of  $A^n$  is disconnected if and only if there exist radical ideals  $a$  and  $b$  such that  $V$  is the disjoint union of  $V(a)$  and  $V(b)$ , so

$$\begin{cases} V = V(\mathfrak{a}) \cup V(\mathfrak{b}) = V(\mathfrak{a} \cap \mathfrak{b}) & \Longleftrightarrow \mathfrak{a} \cap \mathfrak{b} = I(V) \\ \emptyset = V(\mathfrak{a}) \cap V(\mathfrak{b}) = V(\mathfrak{a} + \mathfrak{b}) & \Longleftrightarrow \mathfrak{a} + \mathfrak{b} = k[X\_1, \dots, X\_n]. \end{cases}$$

Then

$$k[V] \simeq \frac{k[X\_1, \ldots, X\_n]}{\mathfrak{a}} \times \frac{k[X\_1, \ldots, X\_n]}{\mathfrak{b}}$$

by Theorem 1.1.

2.34. A Hausdor space is noetherian if and only if it is nite, in which case its irreducible components are the one-point sets.

2.35. In  $k[X\_1,..., X\_n]$ , a principal ideal  $(f)$  is radical if and only if  $f$  is square-free, in which case  $f$  is a product of distinct irreducible polynomials,  $\hat{f} = \hat{f\_1} ... \hat{f\_r}$ , and  $(\hat{f}) = (\hat{f\_1}) \cap ... \cap (\hat{f\_r})$ .

☐